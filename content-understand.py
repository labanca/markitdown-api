from azure.ai.contentunderstanding import ContentUnderstandingClient
from azure.ai.contentunderstanding.models import AnalysisInput
from azure.core.credentials import AzureKeyCredential
from dotenv import load_dotenv
import os

load_dotenv()


endpoint = os.getenv("AZURE_CONTENT_UNDERSTANDING_ENDPOINT")
key = os.getenv("AZURE_FOUNDRY_API_KEY")

print(endpoint, key)

client = ContentUnderstandingClient(
    endpoint=endpoint,
    credential=AzureKeyCredential(key)
)

# Abra o arquivo local como bytes
with open("data-raw/2025-12-22_cofin_final.pptx", "rb") as f:
    file_bytes = f.read()

poller = client.begin_analyze(
    analyzer_id="prebuilt-layout",
    inputs=[
        AnalysisInput(
            data=file_bytes,
            mime_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        )
    ],
)

result = poller.result()
print(result)