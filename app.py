function doPost(e) {
  try {
    const token = PropertiesService.getScriptProperties().getProperty("GITHUB_TOKEN");

    if (!token) {
      return ContentService.createTextOutput("Script Error: Missing GITHUB_TOKEN");
    }

    const repo = "dehshat/invoice-tracker";
    const path = "Invoices_Database.csv";

    const url = `https://api.github.com/repos/${repo}/contents/${path}`;

    const response = UrlFetchApp.fetch(url, {
      method: "get",
      headers: {
        Authorization: "Bearer " + token,
        Accept: "application/vnd.github.v3.raw"
      },
      muteHttpExceptions: true
    });

    if (response.getResponseCode() !== 200) {
      return ContentService.createTextOutput("GitHub Error: " + response.getContentText());
    }

    const content = response.getContentText();
    let csvData = Utilities.parseCsv(content);

    if (!csvData || csvData.length === 0) {
      return ContentService.createTextOutput("Script Error: Empty CSV");
    }

    const headers = csvData[0];

    const amcStartIndex = headers.indexOf("AMC Start Date");
    const amcEndIndex = headers.indexOf("AMC End Date");
    let documentTypeIndex = headers.indexOf("Document Type");

    if (amcStartIndex === -1 || amcEndIndex === -1) {
      return ContentService.createTextOutput("Script Error: AMC columns not found");
    }

    if (documentTypeIndex === -1) {
      headers.push("Document Type");
      documentTypeIndex = headers.length - 1;
    }

    for (let i = 1; i < csvData.length; i++) {
      let row = csvData[i];

      while (row.length < headers.length) {
        row.push("");
      }

      let amcStart = cleanCell(row[amcStartIndex]);
      let amcEnd = cleanCell(row[amcEndIndex]);

      if (amcStart === "" && amcEnd === "") {
        row[documentTypeIndex] = "Service Charge";
      } else {
        row[documentTypeIndex] = "Invoice";
      }
    }

    const sheet = SpreadsheetApp.getActiveSpreadsheet().getActiveSheet();

    sheet.clear();

    sheet
      .getRange(1, 1, csvData.length, headers.length)
      .setValues(csvData);

    sheet
      .getRange(1, 1, 1, headers.length)
      .setFontWeight("bold");

    SpreadsheetApp.flush();

    return ContentService.createTextOutput("Sync Successful");

  } catch (err) {
    return ContentService.createTextOutput("Script Error: " + err.toString());
  }
}


function cleanCell(value) {
  if (value === null || value === undefined) {
    return "";
  }

  value = value.toString().trim();

  const badValues = ["null", "none", "nan", "n/a", "na", "-"];

  if (badValues.includes(value.toLowerCase())) {
    return "";
  }

  return value;
}


function doGet(e) {
  return doPost(e);
}
