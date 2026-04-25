import streamlit as st
import google.generativeai as genai
import json
import time
import io
import csv
import requests
from github import Github

# ---------------- SETUP ----------------

genai.configure(api_key=st.secrets["GEMINI_API_KEY"])

g = Github(st.secrets["GITHUB_TOKEN"])
repo = g.get_repo(st.secrets["REPO_NAME"])

APPS_SCRIPT_WEBAPP_URL = st.secrets["APPS_SCRIPT_WEBAPP_URL"]

CSV_FILE_PATH = "Invoices_Database.csv"

EXPECTED_HEADERS = [
    "Buyer Name",
    "Invoice Date",
    "Invoice Number",
    "Description",
    "Model Number",
    "Serial Number",
    "AMC Start Date",
    "AMC End Date",
    "Mode of Payment",
    "Taxable Value",
    "GST Amount",
    "Total Amount",
    "Document Type"
]


# ---------------- HELPERS ----------------

def clean_value(value):
    value = str(value or "").replace("\n", " ").strip()

    if value.lower() in ["null", "none", "nan", "n/a", "na", "-"]:
        return ""

    return value


def build_header_line():
    output = io.StringIO()
    writer = csv.writer(output, quoting=csv.QUOTE_ALL)
    writer.writerow(EXPECTED_HEADERS)
    return output.getvalue().strip()


def build_csv_rows(extracted_data):
    output = io.StringIO()
    writer = csv.writer(output, quoting=csv.QUOTE_ALL)

    for item in extracted_data:
        row = [
            clean_value(item.get("Buyer Name")),
            clean_value(item.get("Invoice Date")),
            clean_value(item.get("Invoice Number")),
            clean_value(item.get("Description")),
            clean_value(item.get("Model Number")),
            clean_value(item.get("Serial Number")),
            clean_value(item.get("AMC Start Date")),
            clean_value(item.get("AMC End Date")),
            clean_value(item.get("Mode of Payment")),
            clean_value(item.get("Taxable Value")),
            clean_value(item.get("GST Amount")),
            clean_value(item.get("Total Amount")),

            # Leave blank. Apps Script will calculate this.
            ""
        ]

        writer.writerow(row)

    return output.getvalue().strip()


def append_csv_in_github(extracted_data):
    new_rows = build_csv_rows(extracted_data)

    try:
        file = repo.get_contents(CSV_FILE_PATH)
        current_content = file.decoded_content.decode("utf-8").strip()

        if not current_content:
            current_content = build_header_line()

        first_line = current_content.split("\n")[0]

        if "Document Type" not in first_line:
            current_content = build_header_line()

        updated_content = current_content + "\n" + new_rows

        repo.update_file(
            path=file.path,
            message="Append new invoice data",
            content=updated_content,
            sha=file.sha
        )

    except Exception:
        new_csv_content = build_header_line() + "\n" + new_rows

        repo.create_file(
            path=CSV_FILE_PATH,
            message="Create invoice database",
            content=new_csv_content
        )


def sync_google_sheet():
    time.sleep(2)

    response = requests.post(
        APPS_SCRIPT_WEBAPP_URL,
        timeout=30
    )

    if response.status_code != 200:
        raise Exception("Google Sheet sync failed: " + response.text)

    if "Sync Successful" not in response.text:
        raise Exception("Google Sheet sync returned error: " + response.text)

    return response.text


def extract_invoice_data(uploaded_file):
    with open("temp.pdf", "wb") as f:
        f.write(uploaded_file.getbuffer())

    doc = genai.upload_file(path="temp.pdf")

    while doc.state.name == "PROCESSING":
        time.sleep(2)
        doc = genai.get_file(doc.name)

    if doc.state.name == "FAILED":
        raise Exception("Gemini file processing failed.")

    prompt = """
    Extract the following data from this invoice. Return the data ONLY as a JSON list of objects.
    Each object in the list should represent one line item from the 'Description of Goods' table.

    Rules for Extraction:
    1. 'Buyer Name': Extract ONLY the hospital name. Remove all address info.
    2. 'Model Number': Extract from the text in brackets, for example 'MEK-6510K'.
    3. 'Serial Number': Extract from the text in brackets, for example '5857'.
    4. 'AMC Start Date': Look at 'AMC Service Contract Term'. Extract the first date.
    5. 'AMC End Date': Extract the second date in the same line.
    6. 'Mode of Payment': From 'Mode/Terms of Payment'.
    7. 'Description': The full text of the item description.
    8. Do NOT create Document Type.

    JSON Keys:
    "Buyer Name",
    "Invoice Date",
    "Invoice Number",
    "Description",
    "Model Number",
    "Serial Number",
    "AMC Start Date",
    "AMC End Date",
    "Mode of Payment",
    "Taxable Value",
    "GST Amount",
    "Total Amount"
    """

    model = genai.GenerativeModel("gemini-3.1-pro-preview")
    response = model.generate_content([doc, prompt])

    raw_json = (
        response.text
        .replace("```json", "")
        .replace("```", "")
        .strip()
    )

    data = json.loads(raw_json)

    if not isinstance(data, list) or len(data) == 0:
        raise Exception("AI did not return valid invoice data.")

    return data


# ---------------- UI ----------------

st.set_page_config(page_title="AI Invoice Processor")

st.title("📄 AI Invoice Processor")

uploaded_file = st.file_uploader("Upload Invoice PDF", type="pdf")

if uploaded_file and st.button("Extract and Sync"):
    try:
        with st.spinner("AI is analyzing invoice..."):
            data = extract_invoice_data(uploaded_file)

        with st.spinner("Appending data to GitHub CSV..."):
            append_csv_in_github(data)

        with st.spinner("Syncing Google Sheet..."):
            sync_result = sync_google_sheet()

        st.success("Synced successfully!")
        st.info(sync_result)
        st.table(data)

    except Exception as e:
        st.error(f"Error: {str(e)}")
