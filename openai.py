#!/bin/env python3
from datetime import datetime
from pathlib import Path
import argparse
import json
import os
import requests
import signal
import sys
import uuid

# Constants
API_BASE_URL = 'https://api.openai.com/v1/chat/completions'
API_MODEL = 'gpt-3.5-turbo'
API_KEY_PATH = Path('~/.openai/apikey').expanduser()
CONVERSATIONS_DIR = Path('~/.openai/conversations/').expanduser()
HEADERS = {}

def signal_handler(signal, frame):
    print('')
    sys.exit(0)

def load_api_key() -> str:
    with API_KEY_PATH.open('r') as f:
        return f.read().strip()


def get_chat_input(prompt: str) -> str:
    sys.stdout.write(prompt)
    sys.stdout.flush()
    return sys.stdin.readline().strip()

def generate_slogan(prompt: str) -> str:
    conversation_history = \
        [ {'role' : 'system', 'content' : 'Summarize text in max three words'}, \
          {'role' : 'user', 'content' : prompt} ]

    response = send_gpt_request(
        conversation_history=conversation_history,
        temperature=0.7,
        max_tokens=10
    )

    # Post-processing
    response = response.lower()
    response = ''.join(c for c in response if c.isalpha() or c.isspace())
    slogan = response.strip().replace(" ", "_")
    
    return slogan


def send_gpt_request(conversation_history, max_tokens : int, temperature: float) -> str:
    data = {
        'messages' : conversation_history,
        'model' : API_MODEL,
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
    current_date = datetime.now().strftime('%Y-%m-%d')
    current_time = datetime.now().strftime("%H-%M-%S")
    timestamp = datetime.now().isoformat()
    CONVERSATIONS_DIR.mkdir(parents=True, exist_ok=True)

    if sys.stdin.isatty():
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
        filename = f'{timestamp}_{slogan}.json'
    

    while True:
        conversation_history.append({'role': 'user', 'content': message})

        response = send_gpt_request(
            conversation_history=conversation_history,
            temperature=args.temperature,
            max_tokens=args.token_limit
        )
        conversation_history.append({'role': 'assistant', 'content': response})
        print(f'ChatGPT: {response}')
        
        with (CONVERSATIONS_DIR / filename).open('w') as f:
            json.dump(conversation_history, f, indent=2)

        if not sys.stdin.isatty():
            # one shot, piped input
            break

        message = get_chat_input('You: ')

if __name__ == '__main__':
    signal.signal(signal.SIGINT, signal_handler)

    parser = argparse.ArgumentParser(description='Interact with ChatGPT.')
    parser.add_argument('-t', '--temperature', type=float, default=1.0, help='Temperature for GPT response.')
    parser.add_argument('-s', '--system', type=str, default='You are a helpful assistant', help='System message to start the conversation.')
    parser.add_argument('-l', '--token_limit', type=int, default=None, help='Token limit for GPT response.')
    parser.add_argument('-f', '--file', type=str, help='Path to the conversation file to continue.')
    parser.add_argument('-d', '--debug', action='store_true', default=False, help='Print headers and bodies sent over HTTP.')

    args = parser.parse_args()

    main()
