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
        schemes_text = ""
        for point in search_results:
            payload = point.payload
            schemes_text += (
                f"Scheme Name: {payload.get('scheme_name', 'N/A')}\n"
                f"Description: {payload.get('details', 'N/A')}\n"
                f"Eligibility Criteria: {payload.get('eligibility', 'N/A')}\n"
                f"Benefits: {payload.get('benefits', 'N/A')}\n"
                f"Application Process: {payload.get('application', 'N/A')}\n"
                f"Required Documents: {payload.get('documents', 'N/A')}\n"
                f"Level: {payload.get('level', 'N/A')}\n\n"
            )
        # 🤖 3. Groq AI को सीधे कॉल करें (सुपर-फ़ास्ट Llama-3.1-8b-instant मॉडल के साथ)
        system_prompt = (
            "You are an expert Government Scheme Eligibility Engine. Analyze the citizen profile against the provided schemes list. "
            "Return ONLY a clean JSON object with a key 'schemes' containing an array of matched schemes. "
            "Each scheme object MUST have fields: 'title', 'description', 'benefits', 'required_documents' (array), "
            "and 'step_by_step_guidance' (array). Extract the step_by_step_guidance DIRECTLY from the 'Application Process' "
            "text provided for each scheme — break it into individual numbered steps. Do NOT write generic advice like "
            "'visit your nearest CSC' if the Application Process field contains specific steps or URLs. "
            "Do not include any markdown fences like ```json, just return raw JSON."
        )
        
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[...],
            temperature=0.2,
            max_tokens=4000
        )
        
        ai_output = response.choices[0].message.content.strip()
        
        # मार्कडाउन फ़ेंस साफ़ करें अगर एआई ने लगा दिया हो
        if ai_output.startswith("```"):
            ai_output = ai_output.replace("```json", "").replace("```", "").strip()
            
        parsed_json = json.loads(ai_output)
        final_schemes = parsed_json.get("schemes", [])
        
        return {
            "status": "success",
            "schemes": final_schemes
        }
        
    except Exception as e:
        print(f"Error occurred: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    # 🚀 रेंडर के पोर्ट को ज़बरदस्ती कोड से बाइंड करने के लिए यह ब्लॉक सबसे नीचे जोड़ें:
    
if __name__ == "__main__":
    import uvicorn
    # यह रेंडर के एनवायरनमेंट से $PORT खींचेगा, अगर नहीं मिला तो डिफ़ॉल्ट 10000 यूज़ करेगा
    port = int(os.getenv("PORT", 10000)) [INDEX]
    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=False) [INDEX]

