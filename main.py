import streamlit as st
import json
import re
import os
import requests
import ast
from datetime import datetime

import pandas as pd
import plotly.express as px
import io
import contextlib

from dotenv import load_dotenv

# Load environment variables
load_dotenv()
import streamlit as st

GROQ_API_KEY = st.secrets["GROQ_API_KEY"]


# === Load data ===
def load_data(file_path):
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("items", [])

# === Query Detection ===
def is_total_count_query(query):
    return any(k in query.lower() for k in [
       "total count", "how many fabrics", "number of fabrics", "list all fabs",
        "fabric count", "total fabrics", "fabric total", "count of fabrics",
        "count of items", "how many items", "number of articles", "total articles", "total items"
    ])

def is_listing_query(query):
    return any(k in query.lower() for k in [
        "list all", "show all", "show items", "list items", "show records", "fabric list"
    ])


def is_pricing_query(query):
    return any(k in query.lower() for k in [
        "high price", "highest price", "expensive", "quotation", "pricing","which has high pricing","high selling item"," top selling item"
        "quote", "selling price", "costliest", "pricey", "maximum price", "high selling"
    ])


def is_comparison_query(query):
    return any(k in query.lower() for k in [
        "compare", "vs", "versus", "difference between", "diff"
    ])






def is_description_query(query):
    return any(query.lower().startswith(k) for k in [
        "describe", "details of", "info about", "information about", "tell me about"
    ])

def is_brand_query(query): return "brand" in query.lower()
def is_customer_query(query): return "customer" in query.lower()
def is_sales_person_query(query): return "sales person" in query.lower() or "handled by" in query.lower()
def is_sales_team_query(query): return "team" in query.lower() or "sales team" in query.lower()

def extract_keyword(query, field_name):
    parts = query.lower().split(field_name.lower())
    return parts[1].strip(": ").strip() if len(parts) > 1 else query.strip()

# === Logic-based Responses ===
def get_total_count(items): return len(items)

def format_item_summary(item):
    fancyname = item.get("fancyname", "Unknown Fancy Name")
    customer = item.get("customer_name", "Unknown Customer")
    brand = item.get("brand", "Unknown Brand")
    price = item.get("price", "N/A")
    qty = item.get("qty", "N/A")
    salesperson = item.get("sales_person", "Unknown Sales Person")
    
    return (
        f"{fancyname} has customer **{customer}** with quantity **{qty}**, "
        f"price **Rs. {price}**, and belongs to brand **{brand}**. "
        f"Sales handled by **{salesperson}**."
    )


# ✅ MODIFIED: Removed limit, show all results
def list_all_items(items):
    if not items:
        return "No matching records found."
    
    limit = 100
    shown = items[:limit]
    lines = [f"{i+1}. {format_item_summary(item)}" for i, item in enumerate(shown)]
    extra = f"\n\nAnd {len(items) - limit} more not shown." if len(items) > limit else ""
    
    return (
        "There are several records for this team, some are given below:\n\n" +
        "\n".join(lines) + extra
    )


def find_items_by_fancyname(items, keyword):
    matched = [item for item in items if keyword.lower() in (item.get("fancyname") or "").lower()]
    return list_all_items(matched) if matched else None

def find_items_by_field(items, field, keyword):
    matched = [item for item in items if keyword.lower() in (item.get(field, "") or "").lower()]
    return list_all_items(matched) if matched else None


def is_chart_query(query):
    return any(k in query.lower() for k in [
        "chart", "plot", "graph", "visualize", "bar chart", "line chart", "draw", "show trend"
    ])


def compare_two_items_by_fancyname(items, query):
    keywords = re.findall(r'"([^"]+)"|\'([^\']+)\'|(\b\w[\w-]*\b)', query)
    keywords = [k for group in keywords for k in group if k]
    found = []

    for kw in keywords:
        for item in items:
            fn = item.get("fancyname", "").lower()
            if kw.lower() in fn and fn not in found:
                found.append(fn)
                break
        if len(found) >= 2: break

    if len(found) < 2: return None

    def get_best_item(name):
        candidates = [i for i in items if i.get("fancyname", "").lower() == name]
        return max(candidates, key=lambda i: sum(bool(i.get(f)) for f in ["customer_name", "quantity_meters", "selling_price"]), default=None)

    item1, item2 = get_best_item(found[0]), get_best_item(found[1])
    if not item1 or not item2: return None

    def item_summary(item):
        return (
            f"{item.get('fancyname')} | {item.get('composition')} | "
            f"Price: {item.get('selling_price')} {item.get('invoice_currency_code')} | "
            f"Customer: {item.get('customer_name')} | Brand: {item.get('brand')}"
        )

    return f"Comparison:\n- {item_summary(item1)}\n- {item_summary(item2)}"


def get_high_pricing_items(items, top_n=5):
    def parse_price(item):
        try:
            return float(item.get("selling_price") or 0)
        except:
            return 0.0

    sorted_items = sorted(items, key=parse_price, reverse=True)
    top_items = sorted_items[:top_n]

    if not top_items:
        return "No pricing data available to compare."

    lines = ["Here are some of the highest priced fabrics:\n"]
    for i, item in enumerate(top_items):
        fancyname = item.get("fancyname", "Unknown Fancy Name")
        price = item.get("selling_price", "N/A")
        currency = item.get("invoice_currency_code", "")
        customer = item.get("customer_name", "Unknown Customer")
        brand = item.get("brand", "Unknown Brand")
        lines.append(
            f"{i+1}. {fancyname} with selling price {currency} {price}, belong to the "
            f"**{customer},  and brand{brand}"
        )

    return "\n".join(lines)


def clean_text(text):
    # Remove ** and convert to lowercase
    return text.replace("**", "").strip().lower()

def capitalize_sentence(text):
    return text[0].upper() + text[1:] if text else ""

def describe_item_by_fancyname(items, query):
    for prefix in ["describe", "details of", "info about", "information about", "tell me about"]:
        if query.lower().startswith(prefix):
            keyword = query[len(prefix):].strip()
            break
    else:
        keyword = query.strip()

    matched = [
        item for item in items
        if keyword.lower() in (item.get("fancyname") or "").lower()
    ]
    if not matched:
        return "No matching item found."

    responses = []
    for item in matched:
        fancyname = capitalize_sentence(clean_text(item.get("fancyname", "")))
        customer = clean_text(item.get("customer_name", ""))
        brand = clean_text(item.get("brand", ""))
        salesperson = clean_text(item.get("sales_person", ""))
        price = item.get("selling_price", "").strip()
        qty = item.get("quantity_meters", "").strip()
        currency = clean_text(item.get("invoice_currency_code", ""))

        sentence = f"{fancyname} has customer {customer}"
        if price and qty and price.upper() != "N/A" and qty.upper() != "N/A":
            sentence += f" with quantity {qty}, price {currency} {price}"
        sentence += f", and belongs to {brand} brand"
        if salesperson:
            sentence += f". Sales handled by {salesperson}"
        sentence += "."
        responses.append(sentence)

    return "\n".join(responses)




from datetime import datetime

def get_latest_date(items):
    # Parse all trx_date values into datetime objects
    dates = [
        datetime.strptime(item["trx_date"], "%Y-%m-%dT%H:%M:%SZ")
        for item in items if "trx_date" in item
    ]
    if not dates:
        return "unknown date"
    latest_date = max(dates)
    return latest_date.strftime("%Y-%m-%d")


def extract_clean_python_code(text):
    pattern = r"```(?:python)?(.*?)```"
    match = re.search(pattern, text, re.DOTALL)
    if not match:
        return None

    code = match.group(1).strip()

    # Replace JSON read line with DataFrame from `items`
    code = re.sub(r"df\s*=\s*pd\.read_json\([^\)]*\)", "df = pd.DataFrame(items)", code)

    # Add conversion of columns to numeric (handle missing or bad data)
    if "df['total_value']" in code:
        code = code.replace(
            "df['total_value'] = df['selling_price'] * df['quantity_meters']",
            """df['selling_price'] = pd.to_numeric(df['selling_price'], errors='coerce')
df['quantity_meters'] = pd.to_numeric(df['quantity_meters'], errors='coerce')
df = df.dropna(subset=['selling_price', 'quantity_meters'])
df['total_value'] = df['selling_price'] * df['quantity_meters']"""
        )

    return code



# === Fallback to Groq ===
def query_llm_stream(prompt, data=None):
    system_prompt = f"""
You are a smart assistant helping users understand fabric information.
Start with user input and give a helpful, industry-style expert response.
If ask related to listing or any kind of query related to data in json, chng line if u r going to show records also 
if ask like composition of sulphur make it answer like general query, like Sulphur is this and that, chnge line for bullet points
for advantage for anything except data, make it start with the user input not like, this not include in our data bluh bluh
If user asks something like "what are my sales today", calculate the total sales amount, total quantity, and total records for today (based on trx_date). 

if ask like :
which has 11.50 oz
Sample answer: ERNAN brand has 11.50 oz and its has the selling_price of 794.31 with quantity 4434 in meters make it like that


GENERAL BEHAVIOR:
- Always respond naturally and with industry-style helpful tone.
- Never say "data not available" — instead try to infer, explain, or suggest based on general domain knowledge.
- If user asks about a known chemical/fabric/general topic, explain it with bullet points and concise insights.
- When listing records from data, use newlines for each record and format clearly.

DATA BEHAVIOR:
The dataset is JSON with records in `items[]`. Common fields are:
- `fancyname`
- `brand`
- `customer_type` (e.g. EXPORT, LOCAL)
- `selling_price`
- `quantity_meters`
- `trx_date` (in ISO format)

If user asks for:
- "What are my sales today"
- "Total sales for July"
- "Most recent sales this year"
Do this:
1. Use `trx_date` from `items[]`
2. Convert to datetime
3. Find latest trx_date (ignore today’s system date)
4. Filter all records for that same **month and year**
5. Compute:
   - Total sales amount = sum of (`selling_price * quantity_meters`)
   - Total quantity = sum of `quantity_meters`
   - Count of records
6. Respond like:
   - “Most recent sales are for July 2025”
   - “Total sales amount: Rs. XXXX”
   - “Total quantity: XXXX meters”
   - “Records: XX”
7. Then:
   - Find top-selling item (by total value)
   - Suggest: “The item 'VAN GOGH' is the highest-selling. Consider restocking or promoting it.”
   - OR highlight best-performing brand.

EXPORT/BRAND/FANCYNAME Queries:
- For "export", filter `customer_type == EXPORT` and summarize export value by item.
- For "top brands", group by `brand`, sum `selling_price * quantity_meters`, and rank them.
- For "fancyname", list top items based on quantity or sales.

CHARTS:
If user asks:
- "Plot", "chart", "graph", or "visualize":
Return a clean Python code block using Plotly or Matplotlib, showing data from `items[]`.



REMEMBER:
Should give 20 listing
Show tables as newline-formatted lists

Keep user question at the center of your response

Don’t explain what you can’t do — always try to provide something useful

📅 Today’s date is {datetime.now().strftime('%Y-%m-%d')}.


User asked: {prompt}

{f"Here is some sample data:\n{json.dumps(data, indent=2)[:8000]}" if data else ""}
"""
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    body = {
        "model": "llama3-70b-8192",
        "messages": [{"role": "user", "content": system_prompt}],
        "temperature": 0.7,
        "stream": True
    }

    with requests.post(url, headers=headers, json=body, stream=True) as response:
        response.raise_for_status()
        for line in response.iter_lines(decode_unicode=True):
            if not line or line.strip() in ["", "data: [DONE]"]:
                continue
            if line.startswith("data:"):
                try:
                    chunk = json.loads(line.removeprefix("data:").strip())
                    delta = chunk.get("choices", [{}])[0].get("delta", {})
                    if "content" in delta:
                        yield delta["content"]
                except Exception as err:
                    yield f"\n[Error: {err}]"

# === Main Handler ===
def answer_query_with_fallback(items, query):
    if is_total_count_query(query): return f"There are {get_total_count(items)} records."
    if is_listing_query(query): return list_all_items(items)
    if is_comparison_query(query): return compare_two_items_by_fancyname(items, query)
    if is_description_query(query): return describe_item_by_fancyname(items, query)
    if is_pricing_query(query): return get_high_pricing_items(items)
    if is_brand_query(query): return find_items_by_field(items, "brand", extract_keyword(query, "brand"))
    if is_customer_query(query): return find_items_by_field(items, "customer_name", extract_keyword(query, "customer"))
    if is_sales_person_query(query): return find_items_by_field(items, "sales_person", extract_keyword(query, "sales person"))
    if is_sales_team_query(query): return find_items_by_field(items, "sales_team", extract_keyword(query, "team"))
    if is_chart_query(query): return None
    return find_items_by_fancyname(items, query)


# === Streamlit App ===
def main():
    st.title("🧵 Fabric Query Assistant (Manual + Groq Fallback)")

    file_path = os.path.join(os.getcwd(), "sales_data.json")
    try:
        items = load_data(file_path)
        st.success(f"✅ Loaded {len(items)} records.")
    except Exception as e:
        st.error(f"❌ Error loading JSON: {e}")
        return

    query = st.text_input("Ask your question (e.g., 'brand H&M', 'sales person Haris Khan', 'team Farrukh'):")

    if query:
        with st.spinner("Analyzing query..."):
            result = answer_query_with_fallback(items, query)

            if result:
               
                st.text(result)
            else:
           
                response_text = ""
                for chunk in query_llm_stream(query, {"items": items}):
                    response_text += chunk

                # Show full response text regardless
                st.markdown(response_text)

                # Try to extract and execute chart code if it exists
                code = extract_clean_python_code(response_text)
                if code:
                    try:
                        local_vars = {"items": items}
                        stdout_buffer = io.StringIO()
                        with contextlib.redirect_stdout(stdout_buffer):
                            exec(code, {}, local_vars)
                        stdout_output = stdout_buffer.getvalue()

                        # Show print output if any
                        if stdout_output.strip():
                            st.markdown("#### ℹ️ Output Summary:")
                            st.text(stdout_output)

                        # Show chart if available
                        fig = local_vars.get("fig")
                        if fig:
                            st.plotly_chart(fig, use_container_width=True)
                    except Exception as e:
                        st.error(f"⚠️ Couldn't render chart: {e}")



if __name__ == "__main__":
    main()
