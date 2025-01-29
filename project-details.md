We are looking for a software engineer to build an API for a simple app that can take an input of an ASIN, scrape all of the offers in 200 different zip codes, and report on the delivery and shipping window of each of those offers. You will be using ScraperAPI to perform the scrape. You will need to properly parse through the output, normalize the shipping days, and report the data back into a BigQuery table for each zip code and seller.
You will be responsible for the creation of an API, all data engineering, and documentation of the project. We need the operation to complete in under 25 seconds, ideally under 15 seconds if possible.
Here is a GPT written scope that is subject change based on our conversations and your expertise. No frontend work necessary. We will handle that on our end.
Please send hourly price + estimated time you believe this will take you to complete with your proposal.
Thank you.



1. Project Overview
We need a backend solution that:
1. Scrapes Amazon for a given ASIN across ~200 ZIP codes, retrieving all offers (including prices, shipping times, seller info, and Buy Box status).
2. Normalizes delivery estimates for each offer into a single numeric value (e.g., earliest delivery in days).
3. Identifies which offer is winning the Buy Box (if any).
4. Loads all parsed data into BigQuery, where we can query:
• ZIP code - number of days for the fastest shipping
• Which offer is the Buy Box winner
• Per-offer shipping times, sellers, etc.
All responsibilities (scraping, parsing, normalization, data engineering in BigQuery) will be handled by the developer.
2. Functional Requirements
2.1 Inputs
1. ASIN (e.g., "B07XYZ1234") provided via an API endpoint.
2. Optional: Custom list of ZIP codes (default ~200).
2.2 Processing Steps
1. Scrape Amazon
• For each ZIP code, emulate or set that ZIP code location.
• Retrieve the product detail page or “All Offers” page.
• Extract:
• Seller Name / Seller ID
• Price (item + shipping)
• Delivery Estimate (textual date range or day count)
• Prime Eligibility
• Buy Box status (detect who is the “Add to Cart” default).
2. Normalize Delivery Times
• Parse Amazon’s textual estimates (e.g., “Arrives Jan 25–Jan 27” or “Arrives in 2 days”) into numeric day ranges.
• Store at least an earliest day count (minimum days to delivery) for each offer.
• Optionally store a latest day count to reflect the shipping window.
3. Buy Box Detection
• Identify which seller is “Buy Box” winner. (Amazon uses the term “Featured Offer”; typically it’s the default selection on the product page.)
4. Data Engineering & BigQuery
• The developer is responsible for:
• Schema design (creating/maintaining the necessary tables in BigQuery).
• Loading / Inserting the scraping results into BigQuery after each run.
• Ensure the database structure allows queries such as:
• “For each ZIP code, what is the fastest shipping in days (and by which seller)?”
• “Which offer is winning the Buy Box across each ZIP code?”
5. Performance Constraint
• End-to-end process must complete within 25 seconds for a single ASIN across ~200 ZIP codes, under normal conditions.
3. Output Specification
3.1 BigQuery Tables & Fields
Below is a suggested schema for a single table named amazon_offer_details (the developer may refine as needed):
Field Type Description
asin STRING The product’s ASIN.
zip_code STRING ZIP code tested.
seller_id STRING Unique ID for the seller if available.
seller_name STRING Text name of the seller (“Amazon.com,” etc.).
price FLOAT Price of the item alone.
shipping_cost FLOAT Any shipping surcharge if applicable.
prime BOOLEAN True if the offer is Prime-eligible, False otherwise.
earliest_days INT Earliest day count from scrape (e.g., 2 means arrives in 2 days).
latest_days INT Latest day count if a range was given.
buy_box_winner BOOLEAN True if this offer is the Buy Box offer for that ZIP code.
timestamp TIMESTAMP Time the data was scraped/loaded.
Note: The developer can add or modify fields to suit edge cases or additional data (e.g., shipping service level, rating, etc.).
2. Controller
• Loads the default 200 ZIPs if none are provided.
• Spawns concurrent scraping tasks using proxies and user-agent rotation.
3. Scraping Engine
• For each ZIP code:
1. “Set location” to that ZIP.
2. Fetch product detail / offers.
3. Extract shipping info and convert to numeric “days to delivery.”
4. Detect buy box winner.
4. Normalization
• Convert each textual estimate (e.g., “Arrives Jan 25–Jan 27” or “Arrives in 2 days”) into earliest_days and latest_days.
• For date-based text, calculate day difference from “today.”
• For “X–Y days from now,” parse X and Y accordingly.
5. Data Loading
• After all ZIP code scrapes complete, compile data and load into BigQuery:
• Upsert or append (depending on design) with a current timestamp.
• Ensure correct data types.
6. Response to Client
• Return a final JSON to the front end confirming the load success and any relevant summary. (Or optionally return the full dataset, depending on design.)
5. Detailed Deliverables
1. Scraping + Normalization Module
• Must handle concurrency to stay within 25 seconds.
• Convert shipping estimates to numeric day ranges.
2. Buy Box Detection
• Identify which offer is “Add to Cart” default for each ZIP code.
3. BigQuery Integration
• Create necessary tables (if they don’t exist).
• Insert or update records for each (ASIN, ZIP, Offer).
• Provide a short script or code snippet to demonstrate queries for the front end.
4. API Endpoint
• A single or minimal set of endpoints to trigger the scraping + data load.
• Accepts an ASIN and returns JSON with an overview of results (e.g., success/failure, maybe partial data).
5. Documentation
• Explanation of how to set up credentials for BigQuery.
• Steps to run or deploy the service.
• Format of the final JSON response.
• Any error handling or retry logic.
6. Performance & Reliability
1. 25-Second Completion
• Must test typical use on commodity hardware + normal broadband.
• Ensure concurrency with a suitable number of parallel tasks.
2. Error Handling
• Retry logic for Amazon blocks or network issues.
• If a subset of ZIP codes fails, mark them in the final output but proceed with the rest.
3. Logging
• Keep logs (console or centralized) of request statuses, errors, etc.
• Document any critical failures (e.g., captcha or indefinite block from Amazon).
7. Acceptance Criteria
1. Functional
• All Offers for each ZIP code are scraped, including each seller’s shipping details.
• Delivery times are accurately normalized to numeric days.
• Buy Box identification is correct.
• Data is successfully loaded into BigQuery with the agreed-upon schema.
2. Performance
• Under 25 seconds for one ASIN with ~200 ZIP codes.
3. Data Integrity
• 90%+ correctness of shipping-time calculations (spot-check vs. real page).
• No major data type mismatches in BigQuery.
4. Documentation
• Clear instructions for how Neato’s front end should consume the API.
• BigQuery schema definitions, example queries, and usage guidelines.
8. Project Phases & Timeline
1. Phase 1: Basic Scrape & Normalization
• Single ZIP test, parse shipping info, convert to numeric days.
• Insert test data into BigQuery.
2. Phase 2: Scaling to 200 ZIP Codes + Concurrency
• Achieve sub-25-second performance.
• Implement buy box detection.
3. Phase 3: BigQuery Integration & Data Modeling
• Finalize schema, handle upserts/appends.
• Provide test queries and confirm the data structure.
4. Phase 4: Polishing & Error Handling
• Retry logic, partial failures, logging.
• Thorough documentation.
5. Final Handoff: Code, documentation, and any required credentials or environment setups.