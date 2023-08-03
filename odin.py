#!/bin/env python3
from datetime import datetime
from pathlib import Path
import argparse
import json
import os
import requests
import signal
import stat
import sys
import uuid

# Constants
API_BASE_URL = 'https://api.openai.com/v1/chat/completions'
API_DEFAULT_MODEL = 'gpt-3.5-turbo'
API_KEY_PATH = Path('~/.openai/apikey').expanduser()
CONVERSATIONS_DIR = Path('~/.openai/conversations/').expanduser()
HEADERS = {}

def signal_handler(signal, frame):
    if interactive_mode and conversation_file:
        print('')
        print(f'Conversation stored in {conversation_file}')
    print('')
    sys.exit(0)

def load_api_key() -> str:
    # Check for the API key in the OPENAI_APIKEY environment variable first
    api_key = os.environ.get('OPENAI_APIKEY')
    if api_key:
        return api_key.strip()

    # If not found in the environment variable, proceed to look in the file
    if not API_KEY_PATH.exists():
        print('Error: API key not found in environment variable and file not found at the specified location.')
        print('Please ensure that your API key is located at ~/.openai/apikey or set in the OPENAI_APIKEY environment variable.')
        sys.exit(1)

    if API_KEY_PATH.stat().st_mode & (stat.S_IRWXG | stat.S_IRWXO):
        print('Error: API key file should not be accessible '
              '(readable, writable, or executable) by anyone '
              'other than the user.')
        sys.exit(1)

    with API_KEY_PATH.open('r') as f:
        api_key = f.read().strip()

    return api_key


def get_chat_input(prompt: str) -> str:
    sys.stdout.write(prompt)
    sys.stdout.flush()
    return sys.stdin.readline().strip()

def generate_slogan(prompt: str) -> str:
    conversation_history = \
        [ {'role' : 'system',
           'content' :
           'Summarize this text in max three words. The summary should provide '
           'the clearest possible understanding of the text in this minimal '
           'format.'},
          {'role' : 'user', 'content' : prompt} ]

    response = send_gpt_request(
        conversation_history=conversation_history,
        temperature=0.7,
        max_tokens=10,
        model=API_DEFAULT_MODEL
    )

    # Post-processing
    response = response.lower()
    response = ''.join(c for c in response if c.isalpha() or c.isspace())
    slogan = response.strip().replace(' ', '_')

    return slogan


def send_gpt_request(conversation_history, max_tokens : int, temperature: float, model: str) -> str:
    data = {
        'messages' : conversation_history,
        'model' : model,
        'temperature': temperature
    }

    if max_tokens is not None:
        data['max_tokens'] = max_tokens
    print_request_data(data)
    response = requests.post(API_BASE_URL, headers=HEADERS, json=data)
    print_response_data(response.json())
    response.raise_for_status()
    return response.json()['choices'][0]['message']['content'].strip()


def continue_conversation(file_path: Path, system_message: str) -> str:
    with file_path.open('r') as f:
        conversation_history = json.load(f)

    conversation_history.append({'role': 'system', 'content': system_message})
    return conversation_history

def print_request_data(data: dict) -> None:
    if args.debug:
        print('Headers:')
        for key, value in HEADERS.items():
            print(f'{key}: {value}')
        print('\nRequest body:')
        print(json.dumps(data, indent=2))

def print_response_data(data: dict) -> None:
    if args.debug:
        print('Response:')
        print(json.dumps(data, indent=2))

def main():
    HEADERS['Authorization'] = f'Bearer {load_api_key()}'
    CONVERSATIONS_DIR.mkdir(parents=True, exist_ok=True)
    global conversation_file
    conversation_file = None
    global interactive_mode
    interactive_mode = sys.stdin.isatty()

    if interactive_mode:
        message = get_chat_input('You: ')
    else:
        message = sys.stdin.read().strip()

    if args.file:
        file_path = Path(args.file).expanduser()
        conversation_history = continue_conversation(file_path, args.system)
        filename = args.file
    else:
        conversation_history = [{'role': 'system', 'content': args.system}]
        slogan = generate_slogan(message)
        filename = f'{slogan}.json'

         # Append an incrementing integer if filename already exists
        counter = 1
        while (CONVERSATIONS_DIR / filename).exists():
            filename = f'{slogan}_{counter}.json'
            counter += 1

    while True:
        conversation_history.append({'role': 'user', 'content': message})

        response = send_gpt_request(
            conversation_history=conversation_history,
            temperature=args.temperature,
            max_tokens=args.token_limit,
            model=args.model
        )
        conversation_history.append({'role': 'assistant', 'content': response})
        print(f'ChatGPT: {response}')

        if interactive_mode:
            conversation_file = (CONVERSATIONS_DIR / filename)
            with conversation_file.open('w') as f:
                json.dump(conversation_history, f, indent=2)

        if not interactive_mode:
            # one shot, piped input
            break

        message = get_chat_input('You: ')

if __name__ == '__main__':
    conversation_file = None
    interactive_mode = False
    signal.signal(signal.SIGINT, signal_handler)

    parser = argparse.ArgumentParser(description='Interact with ChatGPT.')

    parser.add_argument('-t', '--temperature',
                        type=float,
                        default=1.0,
                        help='Temperature for GPT response.')
    parser.add_argument('-s', '--system',
                        type=str,
                        default='You are a helpful assistant',
                        help='System message to start the conversation.')
    parser.add_argument('-l', '--token_limit',
                        type=int,
                        default=None,
                        help='Token limit for GPT response.')
    parser.add_argument('-f', '--file',
                        type=str,
                        help='Path to the conversation file to continue.')
    parser.add_argument('-m', '--model',
                        type=str,
                        default=API_DEFAULT_MODEL,
                        help='Chat GPT model')
    parser.add_argument('-d', '--debug',
                        action='store_true',
                        default=False,
                        help='Print headers and bodies sent over HTTP.')

    args = parser.parse_args()

    main()
