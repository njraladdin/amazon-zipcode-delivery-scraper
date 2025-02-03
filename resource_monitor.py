import psutil
import time
import threading
from logger import setup_logger
from bandwidth_test import measure_bandwidth

class ResourceMonitor:
    def __init__(self, bandwidth_warning_threshold=0.8, force_bandwidth_test=False, monitor_interval=0.1):
        self.logger = setup_logger('ResourceMonitor')
        self.running = False
        self.monitor_thread = None
        self.bandwidth_warning_threshold = bandwidth_warning_threshold
        self.monitor_interval = monitor_interval  # in seconds
        
        # Stats tracking
        self.stats_history = {
            'upload_usage_pct': [],
            'download_usage_pct': [],
            'connections': [],
            'sent_mbps': [],
            'recv_mbps': []
        }
        
        # Measure initial bandwidth capabilities
        self.bandwidth_limits = self._measure_initial_bandwidth(force_test=force_bandwidth_test)
        if self.bandwidth_limits:
            self.logger.info(f"Bandwidth limits detected:")
            self.logger.info(f"Download: {self.bandwidth_limits['download_mbps']:.2f} Mbps")
            self.logger.info(f"Upload: {self.bandwidth_limits['upload_mbps']:.2f} Mbps")
    
    def _measure_initial_bandwidth(self, force_test=False):
        """Measure initial bandwidth to establish limits"""
        return measure_bandwidth(force_test=force_test)

    def _check_bandwidth_usage(self, current_bandwidth):
        """Check if bandwidth usage is approaching limits"""
        if not self.bandwidth_limits:
            return
        
        upload_usage = current_bandwidth['sent_mbps'] / self.bandwidth_limits['upload_mbps']
        download_usage = current_bandwidth['recv_mbps'] / self.bandwidth_limits['download_mbps']
        
        if upload_usage > self.bandwidth_warning_threshold:
            self.logger.warning(
                f"High upload bandwidth usage: {upload_usage:.1%} of limit "
                f"({current_bandwidth['sent_mbps']:.1f}/{self.bandwidth_limits['upload_mbps']:.1f} Mbps)"
            )
        
        if download_usage > self.bandwidth_warning_threshold:
            self.logger.warning(
                f"High download bandwidth usage: {download_usage:.1%} of limit "
                f"({current_bandwidth['recv_mbps']:.1f}/{self.bandwidth_limits['download_mbps']:.1f} Mbps)"
            )
        
        return {
            'upload_usage_pct': upload_usage * 100,
            'download_usage_pct': download_usage * 100
        }

    def _get_resource_usage(self):
        # Get detailed connection info
        connections = psutil.net_connections()
        conn_states = {
            'ESTABLISHED': 0,
            'TIME_WAIT': 0,
            'CLOSE_WAIT': 0,
            'FIN_WAIT1': 0,
            'FIN_WAIT2': 0,
            'CLOSING': 0
        }
        
        for conn in connections:
            if conn.status in conn_states:
                conn_states[conn.status] += 1

        # Get file descriptors (sockets included)
        try:
            fd_count = psutil.Process().num_fds()  # Unix only
        except AttributeError:
            fd_count = len(psutil.Process().open_files()) + len(connections)  # Windows alternative
        
        # Add bandwidth monitoring
        net_io = psutil.net_io_counters()
        if not hasattr(self, '_last_net_io'):
            self._last_net_io = net_io
            self._last_io_time = time.time()
            bandwidth = {
                'sent_mbps': 0, 
                'recv_mbps': 0,
                'total_sent_gb': round(net_io.bytes_sent / (1024**3), 2),
                'total_recv_gb': round(net_io.bytes_recv / (1024**3), 2)
            }
        else:
            now = time.time()
            time_delta = now - self._last_io_time
            
            # Calculate bandwidth in Mbps
            bytes_sent = net_io.bytes_sent - self._last_net_io.bytes_sent
            bytes_recv = net_io.bytes_recv - self._last_net_io.bytes_recv
            
            bandwidth = {
                'sent_mbps': round((bytes_sent * 8) / (time_delta * 1_000_000), 2),
                'recv_mbps': round((bytes_recv * 8) / (time_delta * 1_000_000), 2),
                'total_sent_gb': round(net_io.bytes_sent / (1024**3), 2),
                'total_recv_gb': round(net_io.bytes_recv / (1024**3), 2)
            }
            
            self._last_net_io = net_io
            self._last_io_time = now

        return {
            'connection_states': conn_states,
            'total_connections': len(connections),
            'file_descriptors': fd_count,
            'socket_errors': self._get_socket_errors(),
            'bandwidth': bandwidth
        }

    def _get_socket_errors(self):
        # Get network interface statistics
        net_stats = psutil.net_if_stats()
        net_io = psutil.net_io_counters()
        return {
            'dropped_packets': getattr(net_io, 'dropin', 0) + getattr(net_io, 'dropout', 0),
            'errors': getattr(net_io, 'errin', 0) + getattr(net_io, 'errout', 0),
            'interface_status': {iface: stats.isup for iface, stats in net_stats.items()}
        }

    def _update_stats_history(self, stats):
        """Update statistics history"""
        if self.bandwidth_limits:
            self.stats_history['upload_usage_pct'].append(stats['bandwidth'].get('upload_usage_pct', 0))
            self.stats_history['download_usage_pct'].append(stats['bandwidth'].get('download_usage_pct', 0))
        
        self.stats_history['connections'].append(stats['total_connections'])
        self.stats_history['sent_mbps'].append(stats['bandwidth']['sent_mbps'])
        self.stats_history['recv_mbps'].append(stats['bandwidth']['recv_mbps'])

    def get_statistics_summary(self):
        """Get summary of collected statistics"""
        summary = {}
        
        for metric, values in self.stats_history.items():
            if not values:
                continue
                
            summary[metric] = {
                'average': sum(values) / len(values),
                'max': max(values),
                'min': min(values),
                'current': values[-1] if values else 0
            }
        
        return summary

    def print_summary(self):
        """Print summary statistics"""
        summary = self.get_statistics_summary()
        
        self.logger.info("\n=== Resource Usage Summary ===")
        
        for metric, stats in summary.items():
            self.logger.info(f"\n{metric.replace('_', ' ').title()}:")
            self.logger.info(f"  Average: {stats['average']:.2f}")
            self.logger.info(f"  Maximum: {stats['max']:.2f}")
            self.logger.info(f"  Minimum: {stats['min']:.2f}")
            self.logger.info(f"  Current: {stats['current']:.2f}")

    def _monitor_loop(self):
        log_counter = 0  # Counter for logging
        while self.running:
            stats = self._get_resource_usage()
            
            # Add bandwidth usage percentage check
            if self.bandwidth_limits:
                usage_stats = self._check_bandwidth_usage(stats['bandwidth'])
                if usage_stats:
                    stats['bandwidth'].update(usage_stats)
            
            # Update statistics history
            self._update_stats_history(stats)
            
            # Only log every second (while monitoring more frequently)
            log_counter += 1
            if log_counter >= (1.0 / self.monitor_interval):
                log_counter = 0
                
                self.logger.info("\n=== Network Resource Usage ===")
                self.logger.info("Connection States:")
                for state, count in stats['connection_states'].items():
                    if count > 0:  # Only log non-zero states
                        self.logger.info(f"  {state}: {count}")
                
                self.logger.info(f"Total Active Connections: {stats['total_connections']}")
                self.logger.info(f"Open File Descriptors: {stats['file_descriptors']}")
                
                if stats['socket_errors']['dropped_packets'] > 0 or stats['socket_errors']['errors'] > 0:
                    self.logger.warning("Network Issues Detected:")
                    self.logger.warning(f"  Dropped Packets: {stats['socket_errors']['dropped_packets']}")
                    self.logger.warning(f"  Network Errors: {stats['socket_errors']['errors']}")
                
                self.logger.info("\nBandwidth Usage:")
                self.logger.info(f"  Upload: {stats['bandwidth']['sent_mbps']} Mbps")
                self.logger.info(f"  Download: {stats['bandwidth']['recv_mbps']} Mbps")
                if self.bandwidth_limits:
                    self.logger.info(f"  Upload Usage: {stats['bandwidth'].get('upload_usage_pct', 0):.1f}%")
                    self.logger.info(f"  Download Usage: {stats['bandwidth'].get('download_usage_pct', 0):.1f}%")
                self.logger.info(f"  Total Sent: {stats['bandwidth']['total_sent_gb']} GB")
                self.logger.info(f"  Total Received: {stats['bandwidth']['total_recv_gb']} GB")
            
            time.sleep(self.monitor_interval)

    def start(self):
        self.running = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()

    def stop(self):
        self.running = False
        if self.monitor_thread:
            self.monitor_thread.join()
        # Print summary when stopping
        self.print_summary() 