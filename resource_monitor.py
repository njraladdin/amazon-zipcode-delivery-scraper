import psutil
import time
import threading
from logger import setup_logger

class ResourceMonitor:
    def __init__(self):
        self.logger = setup_logger('ResourceMonitor')
        self.running = False
        self.monitor_thread = None

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

    def _monitor_loop(self):
        while self.running:
            stats = self._get_resource_usage()
            
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
            self.logger.info(f"  Total Sent: {stats['bandwidth']['total_sent_gb']} GB")
            self.logger.info(f"  Total Received: {stats['bandwidth']['total_recv_gb']} GB")
            
            time.sleep(1)  # Update every second

    def start(self):
        self.running = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()

    def stop(self):
        self.running = False
        if self.monitor_thread:
            self.monitor_thread.join() 