from google.cloud import bigquery
from datetime import datetime
from typing import Dict, List
from logger import setup_logger
import json
import time

class AmazonBigQuery:
    def __init__(self, credentials_path: str):
        """
        Initialize BigQuery client for Amazon offers data
        
        Args:
            credentials_path: Path to Google service account JSON
        """
        self.logger = setup_logger('AmazonBigQuery')
        self.client = None
        self.dataset_id = "amazon_offers"
        self.table_id = "amazon_offer_details"
        self.table_ref = None
        
        # Initialize client and create table
        try:
            self.client = bigquery.Client.from_service_account_json(credentials_path)
            self.table_ref = f"{self.client.project}.{self.dataset_id}.{self.table_id}"
            # Create table immediately - if this fails, the client isn't ready
            self._create_table_if_not_exists()
            self.logger.info("BigQuery client fully initialized with table ready")
        except Exception as e:
            self.logger.error(f"Failed to initialize BigQuery client and create table: {str(e)}")
            raise  # Re-raise to prevent partial initialization

    def _create_table_if_not_exists(self):
        """Create the BigQuery table if it doesn't exist"""
        try:
            # First ensure dataset exists
            dataset = bigquery.Dataset(f"{self.client.project}.{self.dataset_id}")
            dataset.location = "US"
            dataset = self.client.create_dataset(dataset, exists_ok=True)
            self.logger.info(f"Dataset {self.dataset_id} is ready")

            # Check if table exists
            try:
                self.client.get_table(self.table_ref)
                self.logger.info(f"Table {self.table_ref} already exists")
                return
            except Exception:
                self.logger.info(f"Table {self.table_ref} not found, creating new table")
                
            # Create new table
            schema = [
                bigquery.SchemaField("asin", "STRING"),
                bigquery.SchemaField("zip_code", "STRING"),
                bigquery.SchemaField("seller_id", "STRING"),
                bigquery.SchemaField("seller_name", "STRING"),
                bigquery.SchemaField("price", "FLOAT64"),
                bigquery.SchemaField("shipping_cost", "FLOAT64"),
                bigquery.SchemaField("total_price", "FLOAT64"),
                bigquery.SchemaField("prime", "BOOLEAN"),
                bigquery.SchemaField("earliest_days", "INTEGER"),
                bigquery.SchemaField("latest_days", "INTEGER"),
                bigquery.SchemaField("buy_box_winner", "BOOLEAN"),
                bigquery.SchemaField("timestamp", "TIMESTAMP"),
                bigquery.SchemaField("delivery_estimate", "STRING"),
            ]
            
            table = bigquery.Table(self.table_ref, schema=schema)
            table = self.client.create_table(table)
            self.logger.info(f"Successfully created table {self.table_ref}")
                
        except Exception as e:
            self.logger.error(f"Error creating table: {str(e)}")
            raise  # Re-raise to prevent partial initialization

    def _prepare_data_for_upload(self, raw_data: dict) -> dict:
        """Transform raw scraping results into BigQuery-compatible format"""
        return {
            "asin": raw_data["asin"],
            "results": [
                {
                    "asin": raw_data["asin"],
                    "zip_code": result["zip_code"],
                    "timestamp": result.get("timestamp", int(time.time())),
                    "offers_data": [
                        {
                            "seller_id": offer["seller_id"],
                            "seller_name": offer["seller_name"],
                            "price": offer["price"],
                            "shipping_cost": offer.get("shipping_cost", 0.0),
                            "total_price": offer.get("total_price", offer["price"]),
                            "prime": offer["prime"],
                            "earliest_days": offer.get("earliest_days", 0),
                            "latest_days": offer.get("latest_days", 0),
                            "buy_box_winner": offer["buy_box_winner"],
                            "delivery_estimate": offer.get("delivery_estimate", "")
                        }
                        for offer in result.get("offers_data", [])
                    ]
                }
                for result in raw_data["results"] if result and "offers_data" in result
            ]
        }

    def load_offers(self, raw_data: dict) -> bool:
        """Load scraped Amazon offers data into BigQuery"""
        try:
            formatted_data = self._prepare_data_for_upload(raw_data)
            rows_to_insert = []
            
            for zip_result in formatted_data['results']:
                for offer in zip_result['offers_data']:
                    timestamp = datetime.fromtimestamp(zip_result['timestamp']).strftime('%Y-%m-%d %H:%M:%S')
                    
                    row = {
                        'asin': zip_result['asin'],
                        'zip_code': zip_result['zip_code'],
                        'seller_id': offer['seller_id'],
                        'seller_name': offer['seller_name'],
                        'price': offer['price'],
                        'shipping_cost': offer.get('shipping_cost', 0.0),
                        'total_price': offer.get('total_price', offer['price']),
                        'prime': offer['prime'],
                        'earliest_days': offer.get('earliest_days', 0),
                        'latest_days': offer.get('latest_days', 0),
                        'buy_box_winner': offer['buy_box_winner'],
                        'timestamp': timestamp,
                        'delivery_estimate': offer.get('delivery_estimate', '')
                    }
                    rows_to_insert.append(row)

            # Verify table exists before inserting
            try:
                table = self.client.get_table(self.table_ref)
                self.logger.info(f"Found table {self.table_ref}, proceeding with data insertion")
            except Exception as e:
                self.logger.error(f"Table not found before insertion: {str(e)}")
                return False

            # Insert data in batch
            errors = self.client.insert_rows_json(self.table_ref, rows_to_insert)
            
            if errors:
                self.logger.error(f"Errors inserting rows: {errors}")
                return False
                
            self.logger.info(f"Successfully loaded {len(rows_to_insert)} offers")
            return True

        except Exception as e:
            self.logger.error(f"Error loading offers: {str(e)}")
            return False

    def get_fastest_shipping_by_zip(self, asin: str) -> List[Dict]:
        """Get fastest shipping times for each ZIP code"""
        query = f"""
        SELECT 
            zip_code,
            MIN(earliest_days) as fastest_shipping,
            ARRAY_AGG(STRUCT(
                seller_name,
                price,
                earliest_days,
                latest_days
            ) ORDER BY earliest_days ASC LIMIT 1)[OFFSET(0)] as offer_details
        FROM {self.dataset_id}.{self.table_id}
        WHERE asin = @asin
        GROUP BY zip_code
        """
        
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("asin", "STRING", asin)
            ]
        )
        
        try:
            results = list(self.client.query(query, job_config=job_config))
            self.logger.info(f"Successfully retrieved fastest shipping data for {len(results)} ZIP codes")
            return results
        except Exception as e:
            self.logger.error(f"Error querying fastest shipping: {str(e)}")
            return []

    def get_buybox_winners(self, asin: str) -> List[Dict]:
        """Get Buy Box winners across ZIP codes"""
        query = f"""
        SELECT 
            zip_code,
            seller_name,
            price,
            earliest_days,
            latest_days
        FROM {self.dataset_id}.{self.table_id}
        WHERE asin = @asin 
        AND buy_box_winner = TRUE
        """
        
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("asin", "STRING", asin)
            ]
        )
        
        try:
            results = list(self.client.query(query, job_config=job_config))
            self.logger.info(f"Successfully retrieved {len(results)} Buy Box winners")
            return results
        except Exception as e:
            self.logger.error(f"Error querying Buy Box winners: {str(e)}")
            return []


if __name__ == "__main__":
    # Test data
    test_data = {
        "asin": "B01BLUWP1E",
        "results": [
            {
                "asin": "B01BLUWP1E",
                "zip_code": "27101",
                "timestamp": 1738791352,
                "offers_data": [
                    {
                        "seller_id": "AZLEWEBSPAY9I",
                        "buy_box_winner": True,
                        "prime": False,
                        "earliest_days": 4,
                        "latest_days": 4,
                        "price": 3147.0,
                        "shipping_cost": 0.0,
                        "seller_name": "Test Seller"
                    }
                ]
            }
        ]
    }
    
    try:
        # Initialize BigQuery client
        bq = AmazonBigQuery('google-service-account.json')
        
        # Test 1: Load offers
        bq.logger.info("\nTesting load_offers:")
        success = bq.load_offers(test_data)
        bq.logger.info(f"Load successful: {success}")
        
        # Test 2: Query fastest shipping
        bq.logger.info("\nTesting get_fastest_shipping_by_zip:")
        fastest_shipping = bq.get_fastest_shipping_by_zip("B01BLUWP1E")
        for result in fastest_shipping:
            bq.logger.info(f"ZIP: {result.zip_code}, "
                          f"Fastest Shipping: {result.fastest_shipping} days")
        
        # Test 3: Query Buy Box winners
        bq.logger.info("\nTesting get_buybox_winners:")
        buybox_winners = bq.get_buybox_winners("B01BLUWP1E")
        for winner in buybox_winners:
            bq.logger.info(f"ZIP: {winner.zip_code}, "
                          f"Buy Box Winner: {winner.seller_name}, "
                          f"Price: ${winner.price}")
            
    except Exception as e:
        bq.logger.error(f"Error during testing: {str(e)}")