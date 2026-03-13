#!/usr/bin/env python3
import boto3
import json
import os
from dotenv import load_dotenv
load_dotenv()

print("Testing AWS Bedrock access...")

try:
    client = boto3.client(
        service_name='bedrock-runtime',
        region_name='us-west-2',
        aws_access_key_id=os.getenv('AWS_BEDROCK_ACCESS_KEY_ID'),
        aws_secret_access_key=os.getenv('AWS_BEDROCK_SECRET_ACCESS_KEY')
    )

    response = client.invoke_model(
        modelId='us.anthropic.claude-opus-4-5-20251101-v1:0',
        body=json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 100,
            "messages": [{"role": "user", "content": "Say 'Access confirmed!'"}]
        })
    )

    result = json.loads(response['body'].read())
    message = result['content'][0]['text']
    usage = result['usage']

    print(f"✅ Success!")
    print(f"Response: {message}")
    print(f"Tokens used: {usage['input_tokens']} in, {usage['output_tokens']} out")

except Exception as e:
    print(f"❌ Error: {str(e)}")