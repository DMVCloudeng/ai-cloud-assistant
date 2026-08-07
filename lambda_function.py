"""
AI Cloud Assistant - AWS Lambda Function
------------------------------------------
Receives a question via a Lambda Function URL, sends it to the Google
Gemini API (free tier), logs the interaction to DynamoDB, and returns
the AI-generated answer as JSON.

Architecture: Client -> Lambda Function URL -> Lambda -> Gemini API -> DynamoDB -> Response

Environment variables required:
  GEMINI_API_KEY - a free Google Gemini API key (see aistudio.google.com)

DynamoDB table required:
  ai-assistant-log (partition key: request_id, type String)
"""

import json
import os
import urllib.request
import urllib.error
import uuid
import boto3
from datetime import datetime, timezone


def lambda_handler(event, context):
    # Parse the incoming question from the request body
    try:
        body = json.loads(event.get('body', '{}'))
        question = body.get('question', '')
    except (json.JSONDecodeError, TypeError):
        question = ''

    if not question:
        return {
            'statusCode': 400,
            'body': json.dumps({'error': 'Please provide a "question" field.'})
        }

    # Call the Gemini API
    api_key = os.environ['GEMINI_API_KEY']
    url = (
        'https://generativelanguage.googleapis.com/v1beta/models/'
        f'gemini-3.5-flash-lite:generateContent?key={api_key}'
    )

    payload = {
        "contents": [{"parts": [{"text": question}]}]
    }

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode('utf-8'),
        headers={'Content-Type': 'application/json'},
        method='POST'
    )

    try:
        with urllib.request.urlopen(req) as response:
            result = json.loads(response.read().decode('utf-8'))
            answer = result['candidates'][0]['content']['parts'][0]['text']
    except urllib.error.HTTPError as e:
        # Surface Google's detailed error message rather than a generic one.
        # This one change directly revealed a deprecated-model issue during development.
        error_body = e.read().decode('utf-8')
        return {
            'statusCode': 500,
            'body': json.dumps({'error': f'AI request failed: {error_body}'})
        }
    except Exception as e:
        return {
            'statusCode': 500,
            'body': json.dumps({'error': f'AI request failed: {str(e)}'})
        }

    # Log the interaction to DynamoDB
    dynamodb = boto3.resource('dynamodb')
    table = dynamodb.Table('ai-assistant-log')
    request_id = str(uuid.uuid4())

    table.put_item(Item={
        'request_id': request_id,
        'question': question,
        'answer': answer,
        'timestamp': datetime.now(timezone.utc).isoformat()
    })

    return {
        'statusCode': 200,
        'headers': {'Content-Type': 'application/json'},
        'body': json.dumps({
            'question': question,
            'answer': answer,
            'request_id': request_id
        })
    }
