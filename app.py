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

def update_csv_in_github(extracted_data):
    file = repo.get_contents("Invoices_Database.csv")
    current_content = file.decoded_content.decode("utf-8")
    
    output = io.StringIO()
    writer = csv.writer(output, quoting=csv.QUOTE_ALL)
    
    for item in extracted_data:
        # --- Logic for Document Type ---
        start = str(item.get("AMC Start Date", "")).strip()
        end = str(item.get("AMC End Date", "")).strip()
        
        # If both dates exist and aren't empty, it's a Service Charge
        doc_type = "Service Charge" if (start and end) else "Invoice"
        
        row = [
            str(item.get(key, "")).replace("\n", " ").strip() 
            for key in [
                "Buyer Name", "Invoice Date", "Invoice Number", "Description", 
                "Model Number", "Serial Number", "AMC Start Date", "AMC End Date", 
                "Mode of Payment", "Taxable Value", "GST Amount", "Total Amount"
            ]
        ]
        # Append the calculated Document Type
        row.append(doc_type)
        writer.writerow(row)
    
    new_csv_data = output.getvalue()
    updated_content = current_content.rstrip() + "\n" + new_csv_data
    repo.update_file(file.path, "Add invoice entry with Document Type logic", updated_content, file.sha)

# UI
st.set_page_config(page_title="AI Invoice Processor", page_icon="📄")
st.title("📄 AI Invoice Processor")

uploaded_file = st.file_uploader("Upload Invoice PDF", type="pdf")

if uploaded_file and st.button("Extract and Sync"):
    with st.spinner("AI is analyzing the document..."):
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
        4. 'AMC Start Date': Look at the 'Terms of Delivery' or the line 'AMC Service Contract Term'. Extract the first date mentioned (start date).
        5. 'AMC End Date': Extract the second date mentioned in the same line (end date).
        6. 'Mode of Payment': Typically found under 'Mode/Terms of Payment'.
        7. 'Description': The full text of the item description.
        
        JSON Keys required: 
        "Buyer Name", "Invoice Date", "Invoice Number", "Description", "Model Number", "Serial Number", 
        "AMC Start Date", "AMC End Date", "Mode of Payment", "Taxable Value", "GST Amount", "Total Amount"
        """

        model = genai.GenerativeModel('gemini-3.1-pro-preview')
        response = model.generate_content([doc, prompt])
        
        raw_json = response.text.replace("```json", "").replace("```", "").strip()
        try:
            data = json.loads(raw_json)
            update_csv_in_github(data)
            st.success("Successfully synced to GitHub and Google Sheets!")
            st.table(data)
        except Exception as e:
            st.error(f"Error: {e}")
