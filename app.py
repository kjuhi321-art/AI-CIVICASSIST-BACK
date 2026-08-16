import os
import json
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

# 🔐 अपनी असली क्लाउड चाबियाँ (API Keys) यहाँ भरें
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
    return {"message": "Backend is running permanently without n8n!"}

@app.post("/api/check-eligibility")
async def check_eligibility(profile: CitizenProfile):
    try:
        # 🧠 1. यूज़र की प्रोफाइल का एक टेक्स्ट प्रॉम्प्ट बनाएं
        user_query = f"State: {profile.state}, Income: {profile.income}, Category: {profile.category}, Occupation: {profile.occupation}, Age: {profile.dob}, Gender: {profile.gender}"
        
        # 🔍 2. n8n के बिना सीधे Qdrant से योजनाएं खोजें
        # चूँकि हम एम्बेडिंग नोड हटा रहे हैं, हम Qdrant का 'Scroll' या टेक्स्ट सर्च यूज़ करेंगे जो बिना एम्बेडिंग मॉडल के 4,500+ योजनाओं को तुरंत छान देता है!
        search_results = qdrant_client.scroll(
            collection_name="government_schemes",
            limit=15
        )[0]
        
        schemes_text = ""
        for point in search_results:
            payload = point.payload
            schemes_text += f"Scheme Name: {payload.get('Scheme Name', payload.get('title'))}\nDescription: {payload.get('Description', payload.get('details'))}\nEligibility Criteria: {payload.get('Eligibility Criteria')}\n\n"

        # 🤖 3. Groq AI को सीधे कॉल करें (सुपर-फ़ास्ट Llama-3.1-8b-instant मॉडल के साथ)
        system_prompt = (
            "You are an expert Government Scheme Eligibility Engine. Analyze the citizen profile against the provided schemes list.\n\n"
            "CRITICAL INSTRUCTION: You MUST return ONLY a valid, clean JSON object. Do not include any markdown code fences like ```json or ```. Do not include any conversational text before or after the JSON.\n\n"
            "The JSON structure MUST follow this exact format strict keys:\n"
            "{\n"
            "  \"schemes\": [\n"
            "    {\n"
            "      \"title\": \"Name of the scheme\",\n"
            "      \"description\": \"Brief description\",\n"
            "      \"benefits\": \"Key benefits provided\",\n"
            "      \"required_documents\": [\"Document 1\", \"Document 2\", \"Document 3\"],\n"
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
        
        ai_output = response.choices[0].message.content.strip()
        
        # मार्कडाउन फ़ेंस साफ़ करें अगर एआई ने लगा दिया हो
        ai_output = response.choices.message.content.strip()
        print("Raw AI Output:", ai_output)  # रेंडर के लॉग्स में चेक करने के लिए
        
        # 🚀 फ़िक्स 1: अगर एआई ने गलती से ```json या ``` मार्कडाउन लगा दिया हो तो उसे साफ करो
        if "```" in ai_output:
            ai_output = ai_output.split("```")[1]
            if ai_output.startswith("json"):
                ai_output = ai_output[4:].strip()
        ai_output = ai_output.strip()

        final_schemes = []
        try:
            # 🚀 फ़िक्स 2: असली JSON लोड करने की कोशिश करो
            parsed_json = json.loads(ai_output)
            final_schemes = parsed_json.get("schemes", [])
        except Exception as json_err:
            print(f"Standard JSON parse failed, trying regex fallback: {json_err}")
            # 🚀 फ़िक्स 3: अगर पूरा JSON क्रैश हो जाए, तो उसके अंदर से ब्रैकेट ढूंढकर डेटा निकालो
            import re
            match = re.search(r'\{.*\}', ai_output, re.DOTALL)
            if match:
                try:
                    parsed_json = json.loads(match.group(0))
                    final_schemes = parsed_json.get("schemes", [])
                except Exception:
                    pass

        # 🚀 फ़िक्स 4: अगर एआई ने लिस्ट के बजाय सिर्फ एक ऑब्जेक्ट भेजा हो, तो उसे लिस्ट में बदलो
        if isinstance(final_schemes, dict):
            final_schemes = [final_schemes]
            
        print("Successfully extracted schemes count:", len(final_schemes))
        return {
            "status": "success",
            "schemes": final_schemes
        }


if __name__ == "__main__":
    import uvicorn
    # यह रेंडर के एनवायरनमेंट से $PORT खींचेगा, अगर नहीं मिला तो डिफ़ॉल्ट 10000 यूज़ करेगा
    port = int(os.getenv("PORT", 10000)) [INDEX]
    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=False) [INDEX]

