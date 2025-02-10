import asyncio
import aiohttp
import logging
import concurrent.futures
from random import uniform, choice
from twocaptcha import TwoCaptcha
from typing import Optional, List

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

API_ENDPOINT = "https://api.paws.community/v1"

class PawsService:
    def __init__(self, session_name: str, captcha_api_key: str, proxy: str):
        self.session_name = session_name
        self.captcha_api_key = captcha_api_key
        self.proxy = proxy
        # Parse proxy for 2captcha
        proxy_parts = self.proxy.replace('http://', '').split('@')
        auth = proxy_parts[0].split(':')
        proxy_address = proxy_parts[1]
        self.proxy_dict = {
            'type': 'HTTP',
            'uri': proxy_address,
            'username': auth[0],
            'password': auth[1]
        }
        
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

    async def solve_captcha(self) -> dict:
        solver = TwoCaptcha(self.captcha_api_key)
        solver.proxy = self.proxy_dict
        
        for i in range(5):
            try:
                balance = solver.balance()
                if balance > 0.1:
                    logger.info(self.log_message(f'2Captcha Balance: {solver.balance()}'))
                else:
                    logger.warning(self.log_message(f'2Captcha Balance is too low: {balance}'))
                    return {}
                    
                loop = asyncio.get_running_loop()
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    return await loop.run_in_executor(
                        pool,
                        lambda: solver.recaptcha(
                            sitekey="6Lda_s0qAAAAAItgCSBeQN_DVlM9YOk9MccqMG6_",
                            url="https://paws.community/app?tab=claim",
                            version='v2',
                            enterprise=1,
                            userAgent=self.headers['user-agent'],
                            action="submit",
                            softId=4801
                        )
                    )
            except Exception as e:
                logger.warning(self.log_message(f'Failed to solve captcha. Retrying {e}'))
                await asyncio.sleep(uniform(5, 10))
                return await self.solve_captcha()

    async def login(self, session: aiohttp.ClientSession, query_id: str) -> bool:
        try:
            response = await session.post(
                f"{API_ENDPOINT}/user/auth",
                headers=self.headers,
                json={"data": query_id},
                proxy=self.proxy
            )
            
            if response.status not in range(200, 300):
                response_text = await response.text()
                logger.error(self.log_message(f"Login failed with status {response.status}. Response: {response_text}"))
                return False

            data = await response.json()
            token = data.get('data', [None])[0]
            
            if not token:
                logger.error(self.log_message("No token received from login"))
                return False

            self.access_token = token
            self.headers["authorization"] = f"Bearer {token}"
            logger.info(self.log_message("✅ Login successful"))
            return True

        except Exception as e:
            logger.error(self.log_message(f"Error during login: {str(e)}"))
            return False

    async def complete_activity_check(self, session: aiohttp.ClientSession) -> bool:
        recap = await self.solve_captcha()
        if not recap.get('code'):
            logger.error(self.log_message("Failed to get captcha code"))
            return False
                
        payload = {"recaptchaToken": recap.get('code')}
        
        try:
            response = await session.post(
                f"{API_ENDPOINT}/user/activity",
                headers=self.headers,
                json=payload,
                proxy=self.proxy
            )
            
            response_text = await response.text()
            
            if response.status not in range(200, 300):
                logger.error(self.log_message(f"Activity check failed with status {response.status}. Response: {response_text}"))
                return False

            result = await response.json()
            if not (result.get('success') and result.get('data')):
                logger.error(self.log_message(f"Activity check failed. Server response: {result}"))
                return False
                
            return True

        except Exception as e:
            logger.error(self.log_message(f"Activity check error: {str(e)}"))
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

async def process_account(session_name: str, query_id: str, captcha_api_key: str, proxy: str):
    timeout = aiohttp.ClientTimeout(total=60)
    
    # Create ClientSession with proxy configuration
    connector = aiohttp.TCPConnector(ssl=False)
    session = aiohttp.ClientSession(timeout=timeout, connector=connector)
    
    try:
        paws = PawsService(session_name, captcha_api_key, proxy)
        logger.info(f"\nProcessing Account: {session_name}")
        logger.info(f"Using proxy: {proxy}")
        logger.info("-" * 30)

        # Login
        if not await paws.login(session, query_id):
            logger.error(f"❌ Account {session_name} - Login failed")
            return

        # Activity check
        logger.info("Solving captcha and completing activity check...")
        if await paws.complete_activity_check(session):
            logger.info(f"✅ Account {session_name} - Activity check completed")
        else:
            logger.error(f"❌ Account {session_name} - Activity check failed")

    except Exception as e:
        logger.error(f"Error processing account {session_name}: {str(e)}")
    finally:
        await session.close()

async def main():
    try:
        # Get 2captcha API key
        captcha_api_key = os.getenv('TWOCAPTCHA_API_KEY')
        if not captcha_api_key:
            captcha_api_key = input("Enter your 2captcha API key: ")

        # Load proxies
        proxies = load_proxies()
        if not proxies:
            logger.error("No proxies found in proxy.txt")
            return

        # Read accounts from file
        with open('query.txt', 'r') as f:
            query_ids = [line.strip() for line in f if line.strip()]

        logger.info(f"Loaded {len(query_ids)} accounts and {len(proxies)} proxies")

        # Process accounts
        for i, query_id in enumerate(query_ids, 1):
            # Select a random proxy for each account
            proxy = choice(proxies)
            await process_account(f"Account_{i}", query_id, captcha_api_key, proxy)
            
            # Add delay between accounts
            if i < len(query_ids):
                delay = uniform(5, 10)
                logger.info(f"Waiting {delay:.2f}s before next account...")
                await asyncio.sleep(delay)

    except Exception as e:
        logger.error(f"Main error: {str(e)}")

if __name__ == "__main__":
    import os
    asyncio.run(main())
