import os
import json
import re
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from qdrant_client import QdrantClient
from groq import Groq

app = FastAPI()

# CORS सुरक्षा सेटिंग्स
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 🔐 Render के एनवायरनमेंट वेरिएबल्स से चाबियाँ उठाएं
QDRANT_URL = os.getenv("QDRANT_URL")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# क्लाइंट्स चालू करें
try:
    qdrant_client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)
    groq_client = Groq(api_key=GROQ_API_KEY)
except Exception as e:
    print(f"Initialization Error: {e}")

class CitizenProfile(BaseModel):
    fullName: str
    mobileNumber: str
    emailAddress: str
    aadhaarNumber: str
    dob: str
    gender: str
    category: str
    state: str
    district: str
    income: float = 0.0
    occupation: str = ""

@app.get("/")
def home():
    return {"message": "Backend is running flawlessly!"}

@app.post("/api/check-eligibility")
async def check_eligibility(profile: CitizenProfile):
    try:
        # 🧠 1. यूज़र की प्रोफाइल का एक टेक्स्ट प्रॉम्प्ट बनाएं
        user_query = f"State: {profile.state}, Income: {profile.income}, Category: {profile.category}, Occupation: {profile.occupation}, Age: {profile.dob}, Gender: {profile.gender}"
        
        # 🔍 2. Qdrant से योजनाएं खोजें
        search_results = qdrant_client.scroll(
            collection_name="government_schemes",
            limit=15
        )
        
        schemes_text = ""
        for point in search_results[0]: # scroll returns a tuple (points, next_page_offset)
            payload = point.payload
            schemes_text += f"Scheme Name: {payload.get('Scheme Name', payload.get('title'))}\nDescription: {payload.get('Description', payload.get('details'))}\nEligibility Criteria: {payload.get('Eligibility Criteria')}\n\n"

        # 🤖 3. Groq AI के लिए स्ट्रिक्ट गाइडलाइंस प्रॉम्प्ट
        system_prompt = (
            "You are an expert Government Scheme Eligibility Engine. Analyze the citizen profile against the provided schemes list.\n\n"
            "CRITICAL INSTRUCTION: You MUST return ONLY a valid, clean JSON object. Do not include any markdown code fences like ```json or ```. Do not include any conversational text.\n\n"
            "The JSON structure MUST follow this exact format strict keys:\n"
            "{\n"
            "  \"schemes\": [\n"
            "    {\n"
            "      \"title\": \"Name of the scheme\",\n"
            "      \"description\": \"Brief description\",\n"
            "      \"benefits\": \"Key benefits provided\",\n"
            "      \"required_documents\": [\"Caste certificate\", \"Income certificate\", \"Age proof\"],\n"
            "      \"step_by_step_guidance\": [\n"
            "        \"Step 1: Check your eligibility on the official portal.\",\n"
            "        \"Step 2: Gather all required documents like Income and Caste certificates.\",\n"
            "        \"Step 3: Visit your nearest Common Service Center (CSC) or official online desk.\",\n"
            "        \"Step 4: Fill out the application form and submit the documents for verification.\"\n"
            "      ]\n"
            "    }\n"
            "  ]\n"
            "}\n\n"
            "Ensure 'required_documents' and 'step_by_step_guidance' are strictly arrays of strings with multiple separate steps, never a single block of text."
        )
        
        response = groq_client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Citizen Profile:\n{user_query}\n\nAvailable Schemes:\n{schemes_text}"}
            ],
            temperature=0.2
        )
        
        ai_output = response.choices.message.content.strip()
        print("Raw AI Output:", ai_output)
        
        # 🛡️ 4. सुपर-मजबूत रिस्पॉन्स पार्सर (Safe Parser)
        if "```" in ai_output:
            parts = ai_output.split("```")
            for part in parts:
                part_clean = part.strip()
                if part_clean.startswith("json"):
                    ai_output = part_clean[4:].strip()
                    break
                elif part_clean.startswith("{"):
                    ai_output = part_clean
                    break

        ai_output = ai_output.strip()
        final_schemes = []
        
        try:
            parsed_json = json.loads(ai_output)
            final_schemes = parsed_json.get("schemes", [])
        except Exception as json_err:
            print(f"Standard JSON parse failed, trying regex fallback: {json_err}")
            match = re.search(r'\{.*\}', ai_output, re.DOTALL)
            if match:
                try:
                    parsed_json = json.loads(match.group(0))
                    final_schemes = parsed_json.get("schemes", [])
                except Exception:
                    pass

        if isinstance(final_schemes, dict):
            final_schemes = [final_schemes]
            
        print("Successfully extracted schemes count:", len(final_schemes))
        return {
            "status": "success",
            "schemes": final_schemes
        }
        
    except Exception as e:
        print(f"Error occurred: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# 🚀 यह ब्लॉक बिल्कुल बाईं दीवार से सटकर स्वतंत्र रहेगा
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 10000)) [INDEX]
    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=False) [INDEX]
