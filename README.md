# Paws Automation

A Python-based automation tool for managing Paws.community accounts. This tool provides multi-threaded account management, task automation, and proxy support.

## Features

- Multi-threaded account processing
- Proxy support with rotation
- Automatic task completion
- Configurable delays and thread counts
- Colored console logging
- Token management and persistence
- Account status monitoring
- Task blacklisting

## Prerequisites

- Python 3.6+
- Required packages:
  ```
  requests
  colorama
  ```

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/paws-automation.git
   cd paws-automation
   ```

2. Install required packages:
   ```bash
   pip install -r requirements.txt
   ```

## Configuration

The tool uses a `config.json` file for settings. Here's an example configuration:

```json
{
    "use_proxy": false,
    "threads": 50,
    "delay": {
        "min": 2,
        "max": 5
    },
    "tasks": true,
    "referral_code": "your_referral_code",
    "blacklisted_tasks": [
        "task_id_1",
        "task_id_2"
    ]
}
```

### Configuration Options

- `use_proxy`: Enable/disable proxy usage (boolean)
- `threads`: Number of concurrent threads (integer)
- `delay`: Min and max delay between requests in seconds
- `tasks`: Enable/disable task automation (boolean)
- `referral_code`: Your referral code for authentication
- `blacklisted_tasks`: Array of task IDs to skip

## Required Files

1. `query.txt`: Contains account query strings (one per line)
2. `proxy.txt`: List of proxies (if proxy support is enabled)
3. `config.json`: Configuration file
4. `tokens.json`: Automatically generated file for token storage

### Proxy Format
```
http://username:password@ip:port
socks4://ip:port
socks5://ip:port
```

## Usage

1. Set up your configuration in `config.json`
2. Add your account query strings to `query.txt`
3. (Optional) Add proxies to `proxy.txt` if using proxy support
4. Run the script:
   ```bash
   python paws.py
   ```

## Console Output

The tool provides colored console output for different types of messages:
- 🟢 Green: Success messages
- 🔴 Red: Error messages
- 🟡 Yellow: Warnings
- 🔵 Cyan: Information
- ⚪ White: Debug information

## Error Handling

The tool includes comprehensive error handling for:
- Network issues
- Authentication failures
- Invalid tokens
- Proxy errors
- File I/O errors

## Security Notes

- Store your authentication tokens securely
- Don't share your `tokens.json` file
- Be careful when using proxies from untrusted sources
- Review task IDs before blacklisting

## Contributing

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## Disclaimer

This tool is for educational purposes only. Make sure to comply with Paws.community's terms of service and usage policies.

## License

This project is licensed under the MIT License - see the LICENSE file for details.
