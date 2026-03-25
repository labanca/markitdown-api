"""
A sample to demonstrate analyzing with Azure Content Understanding Python SDK.

Requirements:
    - Python 3.9 or later

Setup:
    Follow the steps in the url below to configure your Microsoft Foundry resource and model deployments:
    https://github.com/Azure/azure-sdk-for-python/tree/main/sdk/contentunderstanding/azure-ai-contentunderstanding#configuring-microsoft-foundry-resource

Configuration:
    Before running, update the following variables in the script:
    - AZURE_CONTENT_UNDERSTANDING_ENDPOINT: The endpoint to your Content Understanding resource.
    - CONTENT_UNDERSTANDING_KEY: Your Content Understanding API key (optional if using DefaultAzureCredential).
    - FILE_URL: URL of the file to analyze.

Usage:
    1. Navigate to the directory containing this file:
       cd path/to/the/directory/containing/this/file    # In your terminal

    2. (Optional) Create and activate a virtual environment:
       python -m venv .venv         # One time setup
       source .venv/bin/activate      # On Linux/macOS
       .venv\\Scripts\\activate        # On Windows

    3. Install dependencies:
       python -m pip install azure-ai-contentunderstanding azure-identity

    4. Run the script:
       python sample.py
"""

import sys
import json
import os

import dotenv


from azure.ai.contentunderstanding import ContentUnderstandingClient
from azure.ai.contentunderstanding.models import AnalysisInput, AnalysisResult
from azure.core.credentials import AzureKeyCredential
from azure.core.exceptions import AzureError
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

def main() -> None:

    load_dotenv()

    # Insert the following configurations.
    # 1) AZURE_CONTENT_UNDERSTANDING_ENDPOINT - the endpoint to your Content Understanding resource.
    endpoint = "https://aid-splor-default-resource.services.ai.azure.com/"

    # 2) CONTENT_UNDERSTANDING_KEY - your Content Understanding API key (optional if using DefaultAzureCredential).
    key = os.getenv("AZURE_FOUNDRY_API_KEY")

    # 3) FILE_URL - you can replace this with your own URL.
    file_url = "https://contentunderstanding.ai.azure.com/assets/prebuilt/layout_checklist.jpg"

    # ANALYZER_ID - the ID of the analyzer to use.
    analyzer_id = "prebuilt-layout"

    # API_VERSION - the API version to use.
    api_version = "2025-11-01"

    # Set up Content Understanding client.
    credential = AzureKeyCredential(key) if key and "{{CONTENT_UNDERSTANDING_KEY}}" not in key else DefaultAzureCredential()
    client = ContentUnderstandingClient(endpoint=endpoint, credential=credential, api_version=api_version)

    # [START analyze]
    print(f"Analyzing with {analyzer_id} analyzer...")
    print(f"  File URL: {file_url}\n")
    print(f"{key=}")

    try:
        poller = client.begin_analyze(
            analyzer_id=analyzer_id,
            inputs=[AnalysisInput(url=file_url)],
        )
        result: AnalysisResult = poller.result()
    except AzureError as err:
        print(f"[Azure Error]: {err.message}")
        sys.exit(1)
    except Exception as ex:
        print(f"[Unexpected Error]: {ex}")
        sys.exit(1)
    # [END analyze]

    # [START output_result]
    print("=" * 50)
    print("Analysis result:")
    print("=" * 50 + "\n")

    max_display_lines = 50
    result_str = json.dumps(result.as_dict(), indent=2)
    ret_lines = result_str.splitlines()

    if len(ret_lines) > max_display_lines:
        print("\n".join(ret_lines[:max_display_lines]))
        print(f"\n {len(ret_lines) - max_display_lines} more lines to be displayed...\n")
    else:
        print(result_str)
    # [END output_result]


if __name__ == "__main__":
    main()