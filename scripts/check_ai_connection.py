"""Optional tiny OpenAI connectivity probe; no key or response content is printed."""
from __future__ import annotations
import os
from importlib.metadata import PackageNotFoundError, version
from dotenv import load_dotenv

load_dotenv()
print('SupportFlow AI connection check')
for package in ('openai', 'autogen-agentchat', 'autogen-ext'):
    try:
        print(f'{package}: {version(package)}')
    except PackageNotFoundError:
        print(f'{package}: NOT INSTALLED')

key=os.getenv('OPENAI_API_KEY','').strip()
model=os.getenv('SUPPORTFLOW_AI_MODEL','gpt-4o-mini').strip()
if not key:
    raise SystemExit('OPENAI_API_KEY not found. Check your .env in the project root.')
print(f'API key: present (not displayed) | Model: {model}')
print('Making one short model request to test authentication and connectivity...')
try:
    from openai import OpenAI
    client=OpenAI(api_key=key,timeout=25)
    result=client.chat.completions.create(
        model=model, messages=[{'role':'user','content':'Respond with the word OK only.'}],
        max_tokens=8,
    )
    if not result.choices:
        raise RuntimeError('OpenAI returned no choices')
    print('PASS: OpenAI chat completion worked.')
except Exception as exc:
    name=type(exc).__name__
    detail={'AuthenticationError':'The API key was rejected.',
            'RateLimitError':'Rate limit or insufficient quota; check billing.',
            'PermissionDeniedError':'This account cannot use the model.',
            'NotFoundError':'The configured model was not found or cannot be accessed.',
            'APIConnectionError':'Could not connect to OpenAI.',
            'APITimeoutError':'OpenAI timed out.'}.get(name,'See server terminal traceback for details.')
    print(f'FAIL: {name}: {detail}')
    raise SystemExit(1) from None
