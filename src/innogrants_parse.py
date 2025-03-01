#!/usr/bin/env python3
from bs4 import BeautifulSoup
import os 
import sys
import sqlite3
from dotenv import load_dotenv
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from config.constants import INNOGRANTS_DB_PATH, INNOGRANTS_HTML_FILE, INNOGRANTS_URL, SLACK_CHANNEL


def parse_sections_from_html(html_content):
    """
    Parse the HTML content and return a list of section dictionaries.
    Each section is defined by a button with the class "collapse-title".
    For each section, we extract the title (button text) and its data-target attribute.
    """
    soup = BeautifulSoup(html_content, "html.parser")
    sections = []
    for btn in soup.find_all("button", class_="collapse-title"):
        if "footer-title" in btn.get("class", []):
            continue

        title = btn.get_text(strip=True)
        data_target = btn.get("data-target", "").strip()
        if data_target:
            sections.append({"title": title, "data_target": data_target})
    return sections

def init_db(db_path):
    """
    Initialize the SQLite database and create the 'sections' table if it doesn't exist.
    The table stores a unique data_target and the section title.
    If the table is empty (i.e., newly created), insert default rows with titles:
    "2024", "2023", ..., "2009", "2008 - 2005". In the future, more years can be added.
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT UNIQUE,
            data_target TEXT
        )
    ''')
    conn.commit()

    # Check if the table is empty
    cursor.execute("SELECT COUNT(*) FROM sections")
    count = cursor.fetchone()[0]
    if count == 0:
        # List of default titles to insert
        default_titles = [
            "2024", "2023", "2022", "2021", "2020", "2019", "2018",
            "2017", "2016", "2015", "2014", "2013", "2012", "2011",
            "2010", "2009", "2008 – 2005"
        ]
        # Insert each default row; data_target is set to an empty string (or adjust as needed)
        for title in default_titles:
            cursor.execute(
                "INSERT INTO sections (title, data_target) VALUES (?, ?)", 
                (title, "")
            )
        conn.commit()

    return conn

def get_known_sections(conn):
    """
    Retrieve a dictionary of known sections from the database,
    keyed by their data_target.
    """
    cursor = conn.cursor()
    cursor.execute('SELECT title, data_target FROM sections')
    return {row[0]: row[1] for row in cursor.fetchall()}

def add_sections(conn, sections):
    """
    Insert a new section into the database.
    Uses the data_target as a unique identifier.
    """
    cursor = conn.cursor()
    cursor.executemany('INSERT OR IGNORE INTO sections (title, data_target) VALUES (?, ?)',
                      [(section["title"], section["data_target"]) for section in sections])
    conn.commit()

def parse_startups_from_html(html_content, data_title, data_target):
    """
    Parse the HTML content and return a list of dictionaries representing each row
    of metadata from the cohort table for the given section (data_title).
    
    data_target: The data-target attribute of the button corresponding to the section.
    
    The parser is generic and:
      - Uses its data-target attribute to locate the corresponding collapsible div.
      - Finds the first table within that div.
      - Dynamically extracts header names and associates each data cell with the header.
      - If a cell contains an <a> tag, its value is a dictionary with "text" and "link".

    If the HTML structure changes, this function may need to be updated.
    """
    soup = BeautifulSoup(html_content, "html.parser")

    if not data_target:
        print(f"No data-target attribute found for the cohort {data_title}.")
        return []

    collapse_id = data_target.lstrip('#')
    cohort_div = soup.find("div", id=collapse_id)
    if not cohort_div:
        print(f"No cohort div found with id {collapse_id}.")
        return []

    # Locate the first table in the collapsible section.
    table = cohort_div.find("table")
    if not table:
        print("No table found in the cohort section.")
        return []

    # Find the header row (first <tr> that contains <th> or <td> elements).
    header_row = None
    for tr in table.find_all("tr"):
        if tr.find("th") or tr.find("td"):
            header_row = tr
            break
    if not header_row:
        print("No header row found in the table.")
        return []

    headers = [th.get_text(strip=True) for th in header_row.find_all(["th", "td"])]

    rows_data = []
    # Process each data row (rows after the header)
    for tr in table.find_all("tr"):
        # Skip header row by checking if it contains <th> elements.
        if tr == header_row:
            continue
        cells = tr.find_all("td")
        if not cells:
            continue
        row_dict = {}
        # If there are more cells than headers, zip will stop at the length of headers.
        for header, cell in zip(headers, cells):
            a_tag = cell.find("a")
            if a_tag:
                text = a_tag.get_text(strip=True)
                link = a_tag.get("href", "").strip()
                cell_value = {"text": text, "link": link}
            else:
                cell_value = cell.get_text(strip=True)
            row_dict[header] = cell_value
        rows_data.append(row_dict)

    return rows_data

def format_row(row):
    """
    Format a row dictionary into a single string.
    If a cell value is a dictionary with a link, it uses Slack's markdown link format.
    """
    parts = []
    for header, value in row.items():
        if isinstance(value, dict):
            if value.get("link"):
                # Use Slack link formatting: <URL|Text>
                cell_str = f"• {header}: <{value.get('link')}|{value.get('text', '')}>"
            else:
                cell_str = f"• {header}: {value.get('text', '')}"
        else:
            cell_str = f"{header}: {value}"
        parts.append(cell_str)
    # Joining with newlines to output each bullet on its own line.
    return ", ".join(parts)

def read_html_file(file_path):
    """Read and return the content of the given HTML file."""
    with open(file_path, 'r', encoding='utf-8') as f:
        return f.read()

def send_slack_messages(token, channel, messages):
    """Send a message to a Slack channel using the provided token."""
    client = WebClient(token=token)
    for message in messages:
        try:
            client.chat_postMessage(
                channel=channel,
                text=message,
                unfurl_links=False,
                unfurl_media=False
            )
            print("Message sent successfully!")
        except SlackApiError as e:
            print(f"Error sending message: {e.response['error']}")

def main():
    load_dotenv()

    try:
        html_content = read_html_file(INNOGRANTS_HTML_FILE)
    except Exception as e:
        print(f"Error reading HTML file: {e}")
        sys.exit(1)

    # Parse all sections from the HTML content
    sections = parse_sections_from_html(html_content)
    if not sections:
        print("No sections found in the HTML file.")
        sys.exit(0)
    
    db = init_db(INNOGRANTS_DB_PATH)
    known_sections = get_known_sections(db)

    # Identify new sections (not in the database yet)
    new_sections = [section for section in sections if section["title"] not in known_sections]

    if not new_sections:
        print("No new sections found.")
        sys.exit(0)

    add_sections(db, new_sections)

    messages = []

    for section in new_sections:
        section_startup_data = parse_startups_from_html(html_content, section["title"], section["data_target"])
    
        if section_startup_data:
            message_lines = [f"Innogrants startups for cohort {section['title']}:"]
            for row in section_startup_data:
                message_lines.append(format_row(row))
            message = "\n".join(message_lines)

        else:
            # In case we fail to parse the startup data we can still notify of a new cohort
            message = (f"New Innogrants batch available! Check out the {section['title']} cohort for the latest startup projects.\n")
            message += f"\n\nWarning: Unable to parse startup data for {section['title']} cohort, the script may need to be updated."
    
        # Append the innogrants list URL at the end of the message
        message += f"\n\nFor more details, visit: {INNOGRANTS_URL}"
        messages.append(message)

    slack_token = os.getenv("SLACK_BOT_TOKEN")
    send_slack_messages(slack_token, SLACK_CHANNEL, messages)

if __name__ == "__main__":
    main()