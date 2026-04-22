import streamlit as st
import google.generativeai as genai
import pandas as pd
import json, time, io
from github import Github

# Setup
genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
g = Github(st.secrets["GITHUB_TOKEN"])
repo = g.get_repo(st.secrets["REPO_NAME"])

def update_csv_in_github(extracted_data):
    file = repo.get_contents("Invoices_Database.csv")
    current_content = file.decoded_content.decode("utf-8")
    
    # Convert extracted JSON items to CSV rows
    new_rows = []
    for item in extracted_data:
        row = [str(item.get(key, "")) for key in [
            "Buyer Name", "Invoice Date", "Invoice Number", "Description", 
            "Model Number", "Serial Number", "AMC Start Date", "AMC End Date", 
            "Mode of Payment", "Taxable Value", "GST Amount", "Total Amount"
        ]]
        new_rows.append(",".join(row))
    
    updated_content = current_content + "\n" + "\n".join(new_rows)
    repo.update_file(file.path, "Add invoice entry", updated_content, file.sha)

# UI
st.title("📄 AI Invoice Processor")
uploaded_file = st.file_uploader("Upload Invoice PDF", type="pdf")

if uploaded_file and st.button("Extract and Sync"):
    with st.spinner("AI is analyzing the document..."):
        # Gemini Upload
        with open("temp.pdf", "wb") as f: f.write(uploaded_file.getbuffer())
        doc = genai.upload_file(path="temp.pdf")
        while doc.state.name == "PROCESSING": time.sleep(2); doc = genai.get_file(doc.name)

        # EXACT PROMPT PROVIDED
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
        data = json.loads(raw_json)

        update_csv_in_github(data)
        st.success("Successfully synced to GitHub and Google Sheets!")
        st.table(data)
