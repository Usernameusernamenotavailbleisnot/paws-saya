import requests
import json
import time
import os
from datetime import datetime
import random
import threading
from queue import Queue
import urllib.parse
from requests.exceptions import RequestException
from time import sleep
import traceback
from concurrent.futures import ThreadPoolExecutor
from colorama import init, Fore, Style

# Initialize colorama for cross-platform colored output
init()

# Default headers for all requests
DEFAULT_HEADERS = {
    'accept': 'application/json',
    'accept-language': 'en-US,en;q=0.9',
    'content-type': 'application/json',
    'origin': 'https://app.paws.community',
    'priority': 'u=1, i',
    'referer': 'https://app.paws.community/',
    'sec-ch-ua': '"Microsoft Edge";v="131", "Chromium";v="131", "Not_A Brand";v="24", "Microsoft Edge WebView2";v="131"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"Windows"',
    'sec-fetch-dest': 'empty',
    'sec-fetch-mode': 'cors',
    'sec-fetch-site': 'same-site',
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0'
}

class Logger:
    def __init__(self, lock):
        self.lock = lock

    def log(self, message, level="INFO", username="System", ip="unknown"):
        with self.lock:
            current_time = datetime.now().strftime("%H:%M:%S")
            
            # Color mapping
            colors = {
                "SUCCESS": Fore.GREEN,
                "ERROR": Fore.RED,
                "WARNING": Fore.YELLOW,
                "INFO": Fore.CYAN,
                "DEBUG": Fore.WHITE
            }
            
            color = colors.get(level, Fore.WHITE)
            
            # Format the log message
            log_message = f"[{current_time}] [{level}] [{username}@{ip}] {message}"
            colored_message = f"{color}{log_message}{Style.RESET_ALL}"
            
            # Print to console with color
            print(colored_message)

class PawsAutomation:
    def __init__(self):
        self.lock = threading.Lock()
        self.logger = Logger(self.lock)
        self.load_config()
        self.base_url = "https://api.paws.community/v1"
        self.proxies = self.load_proxies() if self.config['use_proxy'] else []

    def load_config(self):
        try:
            with open('config.json', 'r') as f:
                self.config = json.load(f)
                self.logger.log("Configuration loaded successfully", "SUCCESS")
        except FileNotFoundError:
            self.config = {
                "use_proxy": False,
                "threads": 3,
                "delay": {
                    "min": 2,
                    "max": 5
                },
                "tasks": False,
                "referral_code": "ss0WegUb",
                "blacklisted_tasks": [
                    "6740b2cb15bd1d26b7b71266",
                    "6727ca831ee144b53eb8c08c",
                    "671b8ecb22d15820f13dc61a",
                    "6714e8b80f93ce482efae727"
                ]
            }
            self.save_config()
            self.logger.log("Created new configuration file", "INFO")

    def save_config(self):
        with open('config.json', 'w') as f:
            json.dump(self.config, f, indent=4)

    def load_tokens(self):
        try:
            with open('tokens.json', 'r') as f:
                content = f.read().strip()
                if content:
                    return json.loads(content)
                return {}
        except FileNotFoundError:
            with open('tokens.json', 'w') as f:
                json.dump({}, f)
            return {}
        except json.JSONDecodeError:
            self.logger.log("Tokens file corrupt, recreating...", "WARNING")
            with open('tokens.json', 'w') as f:
                json.dump({}, f)
            return {}

    def save_tokens(self, tokens):
        try:
            with open('tokens.json', 'w') as f:
                json.dump(tokens, f, indent=4)
        except Exception as e:
            self.logger.log(f"Error saving tokens: {str(e)}", "ERROR")

    def load_proxies(self):
        try:
            with open('proxy.txt', 'r') as f:
                return [line.strip() for line in f if line.strip()]
        except FileNotFoundError:
            self.logger.log("proxy.txt not found!", "WARNING")
            return []

    def get_proxy(self):
        if not self.proxies:
            return None
        proxy = random.choice(self.proxies)
        
        if proxy.startswith('socks4://') or proxy.startswith('socks5://'):
            return {
                'http': proxy,
                'https': proxy
            }
        else:
            if not proxy.startswith('http://') and not proxy.startswith('https://'):
                proxy = f'http://{proxy}'
            return {
                'http': proxy,
                'https': proxy.replace('http://', 'https://')
            }

    def check_ip(self, session):
        try:
            response = session.get('https://ipinfo.io/json', headers=DEFAULT_HEADERS)
            if response.status_code == 200:
                data = response.json()
                return data.get('ip', 'Unknown')
        except Exception:
            return 'Error'

    def validate_token(self, session, username, current_ip):
        try:
            response = session.get(f"{self.base_url}/user", headers=DEFAULT_HEADERS)
            return response.status_code == 200
        except Exception as e:
            self.logger.log(f"Token validation failed: {str(e)}", "ERROR", username, current_ip)
            return False

    def authenticate(self, session, query_text, username, current_ip):
        try:
            payload = {
                "data": query_text,
                "referralCode": self.config['referral_code']
            }
            
            headers = DEFAULT_HEADERS.copy()
            
            response = session.post(
                f"{self.base_url}/user/auth",
                json=payload,
                headers=headers
            )
            
            if response.status_code == 201:
                resp_data = response.json()
                token = resp_data['data'][0]
                self.logger.log("Authentication successful", "SUCCESS", username, current_ip)
                return token
            else:
                self.logger.log(f"Authentication failed: {response.text}", "ERROR", username, current_ip)
                return None
                
        except Exception as e:
            self.logger.log(f"Authentication error: {str(e)}", "ERROR", username, current_ip)
            return None

    def process_tasks(self, session, username, current_ip):
            if not self.config['tasks']:
                return

            try:
                response = session.get(f"{self.base_url}/quests/list", headers=DEFAULT_HEADERS)
                
                if response.status_code != 200:
                    self.logger.log(f"Failed to fetch tasks. Status code: {response.status_code}", "ERROR", username, current_ip)
                    return

                tasks = response.json()['data']
                completed_count = 0

                for task in tasks:
                    # Skip if task is in blacklist
                    if task['_id'] in self.config['blacklisted_tasks']:
                        self.logger.log(f"Skipping blacklisted task: {task['title']}", "INFO", username, current_ip)
                        continue

                    if task['progress']['claimed']:
                        continue

                    try:
                        complete_response = session.post(
                            f"{self.base_url}/quests/completed",
                            json={"questId": task['_id']},
                            headers=DEFAULT_HEADERS
                        )

                        if complete_response.status_code == 201:
                            claim_response = session.post(
                                f"{self.base_url}/quests/claim",
                                json={"questId": task['_id']},
                                headers=DEFAULT_HEADERS
                            )

                            if claim_response.status_code == 201:
                                completed_count += 1
                                self.logger.log(f"Task completed and claimed: {task['title']}", "SUCCESS", username, current_ip)
                            else:
                                self.logger.log(f"Failed to claim task. Status: {claim_response.status_code}", "ERROR", username, current_ip)
                        else:
                            self.logger.log(f"Failed to complete task. Status: {complete_response.status_code}", "ERROR", username, current_ip)

                        time.sleep(random.uniform(self.config['delay']['min'], self.config['delay']['max']))

                    except Exception as e:
                        self.logger.log(f"Error processing task {task['_id']}: {str(e)}", "ERROR", username, current_ip)

                if completed_count > 0:
                    self.logger.log(f"Completed {completed_count} tasks", "SUCCESS", username, current_ip)

            except Exception as e:
                self.logger.log(f"Task processing error: {str(e)}", "ERROR", username, current_ip)

    def check_account_status(self, session, username, current_ip):
        try:
            response = session.get(f"{self.base_url}/user", headers=DEFAULT_HEADERS)
            if response.status_code == 200:
                user_data = response.json()['data']
                ##claim_date = datetime.fromtimestamp(user_data['claimStreakData']['lastClaimDate']/1000).strftime('%Y-%m-%d %H:%M:%S')
                ##balance = user_data['gameData']['balance']
                ##self.logger.log(f"Balance: {balance} | Last Claim: {claim_date}", "SUCCESS", username, current_ip)
            else:
                self.logger.log(f"Failed to get account status: {response.text}", "ERROR", username, current_ip)
        except Exception as e:
            self.logger.log(f"Error checking account status: {str(e)}", "ERROR", username, current_ip)

    def process_account(self, query_text):
        session = requests.Session()
        current_ip = 'unknown'
        username = "unknown"

        try:
            if self.config['use_proxy']:
                proxy = self.get_proxy()
                if proxy:
                    session.proxies = proxy
                    current_ip = self.check_ip(session)

            # Parse user data
            params = dict(urllib.parse.parse_qsl(query_text))
            user_data = json.loads(urllib.parse.unquote(params['user']))
            username = user_data.get('username', 'unknown')

            # Authentication
            tokens = self.load_tokens()
            
            if username in tokens:
                session.headers.update({'Authorization': f'Bearer {tokens[username]}'})
                if not self.validate_token(session, username, current_ip):
                    tokens.pop(username, None)
                    self.save_tokens(tokens)

            if username not in tokens:
                token = self.authenticate(session, query_text, username, current_ip)
                if token:
                    tokens[username] = token
                    self.save_tokens(tokens)
                    session.headers.update({'Authorization': f'Bearer {token}'})
                else:
                    return

            # Check account status and process tasks
            self.check_account_status(session, username, current_ip)
            self.process_tasks(session, username, current_ip)

        except Exception as e:
            self.logger.log(f"Critical error: {str(e)}", "ERROR", username, current_ip)
        finally:
            session.close()

def main():
    bot = PawsAutomation()
    
    try:
        with open('query.txt', 'r', encoding='utf-8') as f:
            queries = [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        bot.logger.log("query.txt not found!", "ERROR")
        return

    if not queries:
        bot.logger.log("No queries found in query.txt!", "WARNING")
        return

    thread_count = min(bot.config.get('threads', 3), len(queries))
    bot.logger.log(f"Starting processing with {thread_count} threads for {len(queries)} accounts", "INFO")

    with ThreadPoolExecutor(max_workers=thread_count) as executor:
        futures = [executor.submit(bot.process_account, query) for query in queries]
        for future in futures:
            try:
                future.result()
            except Exception as e:
                bot.logger.log(f"Thread execution error: {str(e)}", "ERROR")

    bot.logger.log("All accounts processed", "SUCCESS")

if __name__ == "__main__":
    main()
