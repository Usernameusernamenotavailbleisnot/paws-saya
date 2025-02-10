import asyncio
import aiohttp
import logging
import concurrent.futures
from random import uniform, choice
from typing import Optional, List
from concurrent.futures import ThreadPoolExecutor
import time
import os
import json

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

API_ENDPOINT = "https://api.paws.community/v1"
CAPSOLVER_API_ENDPOINT = "https://api.capsolver.com"

# Define retryable errors
PROXY_RETRY_ERRORS = [
    "Connection reset by peer",
    "Connection refused",
    "Cannot connect to proxy",
    "Proxy connection timeout",
    "Proxy connection failed",
    "[Errno 104]",
    "[Errno 111]",
    "TimeoutError",
    "ClientConnectorError"
]

class PawsService:
    def __init__(self, session_name: str, capsolver_api_key: str, proxy: str, max_retries: int = 3):
        self.session_name = session_name
        self.capsolver_api_key = capsolver_api_key
        self.proxy = proxy
        self.max_retries = max_retries
        
        # Parse proxy for both HTTP and SOCKS
        proxy_parts = self.proxy.replace('http://', '').replace('socks5://', '').split('@')
        auth = proxy_parts[0].split(':')
        proxy_address = proxy_parts[1]
        
        # Store proxy parts separately
        self.proxy_host = proxy_address.split(':')[0]
        self.proxy_port = proxy_address.split(':')[1]
        self.proxy_username = auth[0]
        self.proxy_password = auth[1]
        
        self.headers = {
            "accept": "application/json",
            "accept-encoding": "gzip, deflate, br, zstd",
            "accept-language": "en-US,en;q=0.8",
            "content-type": "application/json",
            "origin": "https://paws.community",
            "priority": "u=1, i",
            "referer": "https://paws.community/",
            "sec-ch-ua": '"Not(A:Brand";v="99", "Brave";v="133", "Chromium";v="133"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-site",
            "sec-gpc": "1",
            "secure-check": "paws",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36"
        }
        self.access_token = None

    def log_message(self, message) -> str:
        return f"{self.session_name} | {message}"

    def is_retryable_error(self, error: Exception) -> bool:
        error_str = str(error).lower()
        return any(retry_err.lower() in error_str for retry_err in PROXY_RETRY_ERRORS)

    async def solve_captcha(self) -> dict:
        """Solve captcha using Capsolver"""
        try:
            # Prepare the task for Capsolver
            task_payload = {
                "clientKey": self.capsolver_api_key,
                "task": {
                    "type": "ReCaptchaV2Task",
                    "websiteURL": "https://paws.community/app?tab=claim",
                    "websiteKey": "6Lda_s0qAAAAAItgCSBeQN_DVlM9YOk9MccqMG6_",
                    "enterprisePayload": {
                        "s": ""  # Enterprise payload if needed
                    },
                    "proxy": f"http://{self.proxy_username}:{self.proxy_password}@{self.proxy_host}:{self.proxy_port}"
                }
            }

            async with aiohttp.ClientSession() as session:
                # Create task
                create_task_response = await session.post(
                    f"{CAPSOLVER_API_ENDPOINT}/createTask",
                    json=task_payload
                )
                create_task_data = await create_task_response.json()

                if create_task_data.get("errorId") != 0:
                    logger.error(self.log_message(f"Failed to create captcha task: {create_task_data.get('errorDescription')}"))
                    return {}

                task_id = create_task_data.get("taskId")
                
                # Get task result
                for _ in range(30):  # Maximum 30 attempts
                    get_result_response = await session.post(
                        f"{CAPSOLVER_API_ENDPOINT}/getTaskResult",
                        json={
                            "clientKey": self.capsolver_api_key,
                            "taskId": task_id
                        }
                    )
                    result_data = await get_result_response.json()

                    if result_data.get("status") == "ready":
                        return {"code": result_data.get("solution", {}).get("gRecaptchaResponse")}
                    
                    await asyncio.sleep(2)

                logger.error(self.log_message("Captcha solving timeout"))
                return {}

        except Exception as e:
            logger.error(self.log_message(f"Error solving captcha: {e}"))
            return {}

    async def try_login(self, session: aiohttp.ClientSession, query_id: str) -> tuple[bool, Optional[str]]:
        """Attempt a single login request"""
        try:
            response = await session.post(
                f"{API_ENDPOINT}/user/auth",
                headers=self.headers,
                json={"data": query_id},
                proxy=self.proxy,
                timeout=30
            )
            
            response_text = await response.text()
            
            if response.status == 429:  # Rate limit
                return False, "Rate limited"
            
            if response.status not in range(200, 300):
                return False, f"HTTP {response.status}: {response_text}"

            data = await response.json()
            token = data.get('data', [None])[0]
            
            if not token:
                return False, "No token received"

            return True, token

        except asyncio.TimeoutError:
            return False, "Request timeout"
        except Exception as e:
            return False, str(e)

    async def login(self, session: aiohttp.ClientSession, query_id: str) -> bool:
        max_attempts = 5  # Maximum number of login attempts
        base_delay = 3  # Base delay in seconds
        
        for attempt in range(max_attempts):
            logger.info(self.log_message(f"Login attempt {attempt + 1}/{max_attempts}"))
            
            success, result = await self.try_login(session, query_id)
            
            if success:
                self.access_token = result
                self.headers["authorization"] = f"Bearer {result}"
                logger.info(self.log_message("✅ Login successful"))
                return True
            
            # Check if error is retryable
            if any(err in result.lower() for err in PROXY_RETRY_ERRORS):
                delay = base_delay * (attempt + 1) + uniform(1, 3)
                logger.warning(self.log_message(
                    f"Retryable error during login: {result}. "
                    f"Waiting {delay:.2f}s before retry {attempt + 1}"
                ))
                await asyncio.sleep(delay)
                continue
            
            # Handle rate limiting with longer delays
            if "rate limit" in result.lower():
                delay = base_delay * 2 * (attempt + 1) + uniform(2, 5)
                logger.warning(self.log_message(
                    f"Rate limited during login. "
                    f"Waiting {delay:.2f}s before retry {attempt + 1}"
                ))
                await asyncio.sleep(delay)
                continue
                
            # Handle other errors based on response
            if "invalid" in result.lower() or "unauthorized" in result.lower():
                logger.error(self.log_message(f"Login failed - Invalid credentials: {result}"))
                return False
                
            if "timeout" in result.lower():
                delay = base_delay * (attempt + 1) + uniform(1, 3)
                logger.warning(self.log_message(
                    f"Timeout during login. "
                    f"Waiting {delay:.2f}s before retry {attempt + 1}"
                ))
                await asyncio.sleep(delay)
                continue
            
            # For other errors, retry with increasing delay
            delay = base_delay * (attempt + 1) + uniform(1, 3)
            logger.warning(self.log_message(
                f"Login failed: {result}. "
                f"Waiting {delay:.2f}s before retry {attempt + 1}"
            ))
            await asyncio.sleep(delay)
        
        logger.error(self.log_message(f"Login failed after {max_attempts} attempts"))
        return False

    async def complete_activity_check(self, session: aiohttp.ClientSession) -> bool:
        for attempt in range(self.max_retries):
            try:
                # Solve captcha for each attempt
                recap = await self.solve_captcha()
                if not recap.get('code'):
                    logger.error(self.log_message("Failed to get captcha code"))
                    if attempt < self.max_retries - 1:
                        logger.info(self.log_message(f"Retrying captcha (attempt {attempt + 1}/{self.max_retries})"))
                        await asyncio.sleep(uniform(3, 7))
                        continue
                    return False
                    
                payload = {"recaptchaToken": recap.get('code')}
                
                response = await session.post(
                    f"{API_ENDPOINT}/user/activity",
                    headers=self.headers,
                    json=payload,
                    proxy=self.proxy
                )
                
                response_text = await response.text()
                
                if response.status not in range(200, 300):
                    logger.error(self.log_message(f"Activity check failed with status {response.status}. Response: {response_text}"))
                    if attempt < self.max_retries - 1:
                        logger.info(self.log_message(f"Retrying activity check (attempt {attempt + 1}/{self.max_retries})"))
                        await asyncio.sleep(uniform(3, 7))
                        continue
                    return False

                result = await response.json()
                
                # If success is True and data is False, it means activity was already completed
                if result.get('success'):
                    if not result.get('data'):
                        logger.info(self.log_message("✅ Activity was already completed previously"))
                    else:
                        logger.info(self.log_message("✅ Activity check completed successfully"))
                    return True
                
                # If we got here, something went wrong
                logger.error(self.log_message(f"Activity check failed. Server response: {result}"))
                if attempt < self.max_retries - 1:
                    logger.info(self.log_message(f"Retrying due to invalid response (attempt {attempt + 1}/{self.max_retries})"))
                    await asyncio.sleep(uniform(3, 7))
                    continue
                return False

            except Exception as e:
                if self.is_retryable_error(e):
                    logger.warning(self.log_message(f"Retryable error during activity check (attempt {attempt + 1}/{self.max_retries}): {str(e)}"))
                    if attempt < self.max_retries - 1:
                        await asyncio.sleep(uniform(3, 7))
                        continue
                logger.error(self.log_message(f"Activity check error: {str(e)}"))
                return False

        return False

def load_proxies() -> List[str]:
    try:
        with open('proxy.txt', 'r') as f:
            return [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        logger.error("proxy.txt file not found")
        return []
    except Exception as e:
        logger.error(f"Error loading proxies: {str(e)}")
        return []

async def process_account(session_name: str, query_id: str, capsolver_api_key: str, proxy: str):
    timeout = aiohttp.ClientTimeout(total=60)
    
    # Create ClientSession with proxy configuration
    connector = aiohttp.TCPConnector(ssl=False)
    session = aiohttp.ClientSession(timeout=timeout, connector=connector)
    
    try:
        paws = PawsService(session_name, capsolver_api_key, proxy)
        logger.info(f"\nProcessing Account: {session_name}")
        logger.info(f"Using proxy: {proxy}")
        logger.info("-" * 30)

        # Login with retries
        if not await paws.login(session, query_id):
            logger.error(f"❌ Account {session_name} - Login failed")
            return

        # Activity check
        logger.info(f"Account {session_name} - Solving captcha and completing activity check...")
        if await paws.complete_activity_check(session):
            logger.info(f"✅ Account {session_name} - Activity check completed")
        else:
            logger.error(f"❌ Account {session_name} - Activity check failed")

    except Exception as e:
        logger.error(f"Error processing account {session_name}: {str(e)}")
    finally:
        await session.close()

async def process_accounts_chunk(accounts: List[tuple], capsolver_api_key: str, proxies: List[str]):
    tasks = []
    for session_name, query_id in accounts:
        proxy = choice(proxies)
        tasks.append(process_account(session_name, query_id, capsolver_api_key, proxy))
    await asyncio.gather(*tasks)

async def main():
    try:
        # Get Capsolver API key
        capsolver_api_key = os.getenv('CAPSOLVER_API_KEY')
        if not capsolver_api_key:
            capsolver_api_key = input("Enter your Capsolver API key: ")

        # Load proxies
        proxies = load_proxies()
        if not proxies:
            logger.error("No proxies found in proxy.txt")
            return

        # Read accounts from file
        with open('query.txt', 'r') as f:
            query_ids = [line.strip() for line in f if line.strip()]

        logger.info(f"Loaded {len(query_ids)} accounts and {len(proxies)} proxies")

        # Prepare account chunks for parallel processing
        chunk_size = 10  # Process 10 accounts simultaneously
        accounts = [(f"Account_{i}", query_id) for i, query_id in enumerate(query_ids, 1)]
        chunks = [accounts[i:i + chunk_size] for i in range(0, len(accounts), chunk_size)]

        # Process chunks of accounts in parallel
        for chunk_num, chunk in enumerate(chunks, 1):
            logger.info(f"\nProcessing chunk {chunk_num}/{len(chunks)} ({len(chunk)} accounts)")
            await process_accounts_chunk(chunk, capsolver_api_key, proxies)
            
            # Add delay between chunks
            if chunk != chunks[-1]:
                delay = uniform(10, 15)
                logger.info(f"Waiting {delay:.2f}s before next chunk...")
                await asyncio.sleep(delay)

        logger.info("\n✅ All accounts processed!")

    except Exception as e:
        logger.error(f"Main error: {str(e)}")

if __name__ == "__main__":
    asyncio.run(main())
