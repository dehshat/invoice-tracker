import streamlit as st
import google.generativeai as genai
import pandas as pd
import json, time, io
from github import Github
import csv

# Setup
genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
g = Github(st.secrets["GITHUB_TOKEN"])
repo = g.get_repo(st.secrets["REPO_NAME"])

# The exact 13 headers we need
EXPECTED_HEADERS = [
    "Buyer Name", "Invoice Date", "Invoice Number", "Description", 
    "Model Number", "Serial Number", "AMC Start Date", "AMC End Date", 
    "Mode of Payment", "Taxable Value", "GST Amount", "Total Amount", "Document Type"
]

def update_csv_in_github(extracted_data):
    file = repo.get_contents("Invoices_Database.csv")
    current_content = file.decoded_content.decode("utf-8").strip()
    
    # Check if the file is empty or has old/missing headers
    if not current_content or "Document Type" not in current_content.split('\n')[0]:
        # Reset file with correct headers if it's outdated
        header_line = ",".join([f'"{h}"' for h in EXPECTED_HEADERS])
        # If there was old data, we keep it but it might be misaligned; 
        # for a clean start, we just initialize headers.
        current_content = header_line

    output = io.StringIO()
    writer = csv.writer(output, quoting=csv.QUOTE_ALL)
    
    for item in extracted_data:
        # --- Logic for Document Type ---
        # It marks as 'Service Charge' only if both AMC dates exist [cite: 44, 107]
        start = str(item.get("AMC Start Date", "")).strip()
        end = str(item.get("AMC End Date", "")).strip()
        doc_type = "Service Charge" if (start and end) else "Invoice"
        
        row = [
            str(item.get(key, "")).replace("\n", " ").strip() 
            for key in EXPECTED_HEADERS[:-1] # Get first 12 keys
        ]
        row.append(doc_type) # Add the 13th column
        writer.writerow(row)
    
    new_csv_data = output.getvalue()
    # Combine properly to avoid ghost rows
    updated_content = current_content + "\n" + new_csv_data.strip()
    repo.update_file(file.path, "Add entry with corrected headers", updated_content, file.sha)

# UI
st.set_page_config(page_title="AI Invoice Processor")
st.title("📄 AI Invoice Processor")

uploaded_file = st.file_uploader("Upload Invoice PDF", type="pdf")

if uploaded_file and st.button("Extract and Sync"):
    with st.spinner("AI is analyzing..."):
        with open("temp.pdf", "wb") as f:
            f.write(uploaded_file.getbuffer())
        
        doc = genai.upload_file(path="temp.pdf")
        while doc.state.name == "PROCESSING":
            time.sleep(2)
            doc = genai.get_file(doc.name)

        prompt = """
        Extract the following data from this invoice. Return the data ONLY as a JSON list of objects.
        Each object in the list should represent one line item from the 'Description of Goods' table.
        
        Rules for Extraction:
        1. 'Buyer Name': Extract ONLY the hospital name (e.g., 'KALIDAS HOSPITAL'). Remove all address info.
        2. 'Model Number': Extract from the text in brackets (e.g., 'MEK-6510K').
        3. 'Serial Number': Extract from the text in brackets (e.g., '5857').
        4. 'AMC Start Date': Look at 'AMC Service Contract Term'. Extract the first date.
        5. 'AMC End Date': Extract the second date in the same line.
        6. 'Mode of Payment': From 'Mode/Terms of Payment'.
        7. 'Description': The full text of the item description.
        
        JSON Keys: "Buyer Name", "Invoice Date", "Invoice Number", "Description", "Model Number", 
        "Serial Number", "AMC Start Date", "AMC End Date", "Mode of Payment", "Taxable Value", 
        "GST Amount", "Total Amount"
        """

        model = genai.GenerativeModel('gemini-3.1-pro-preview')
        response = model.generate_content([doc, prompt])
        
        raw_json = response.text.replace("```json", "").replace("```", "").strip()
        data = json.loads(raw_json)
        update_csv_in_github(data)
        st.success("Synced! Document Type: " + ("Service Charge" if (data[0].get("AMC Start Date")) else "Invoice"))
        st.table(data)
