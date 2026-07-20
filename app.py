from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import requests
import json

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class CitizenData(BaseModel):
    fullName: str
    mobileNumber: str
    emailAddress: str
    aadhaarNumber: str
    dob: str
    gender: str
    category: str
    state: str
    district: str
    income: str
    occupation: str
    education: str
    disability: str
    bpl: str
    language: str

# ✔️ बिल्कुल सही और 100% असली लिंक (इसे कॉपी करके अपनी फ़ाइल में डालो):
N8N_WEBHOOK_URL = "https://my-civic-n8n.onrender.com/webhook/8f42e641-d1a2-4751-925e-002e918ed2b9"

@app.get("/")
def home():
    return {"message": "Python FastAPI Backend is Running!"}

@app.post("/api/check-eligibility")
def check_eligibility(data: CitizenData):
    print("Received Data Locally for:", data.fullName)
    
    try:
        # Forwarding form payload to n8n workflow
        response = requests.post(N8N_WEBHOOK_URL, json=data.dict(), timeout=20)
        
        if response.status_code == 200:
            res_data = response.json()
            
            # 1. n8n से आने वाले एरे/लिस्ट को संभालें
            if isinstance(res_data, list) and len(res_data) > 0:
                res_data = res_data[0]
                
            # 2. 🚀 मुख्य फिक्स: n8n के 'text' फ़ील्ड से डेटा निकालें
            output_content = res_data.get("text", res_data)
            
            # 3. अगर डेटा स्ट्रिंग है, तो उसे असली JSON में बदलें
            if isinstance(output_content, str):
                output_content = output_content.strip()
                try:
                    output_content = json.loads(output_content)
                except Exception:
                    pass
            
            # 4. फ़्रंटएंड कंपोनेंट्स के लिए डेटा को स्टैंडर्ड फ़ॉर्मेट में लाएं
            final_schemes = []
            if isinstance(output_content, dict):
                if "schemes" in output_content:
                    final_schemes = output_content["schemes"]
                elif "data" in output_content:
                    final_schemes = output_content["data"]
                else:
                    final_schemes = [output_content]
            elif isinstance(output_content, list):
                final_schemes = output_content
                
            return {
                "status": "success",
                "schemes": final_schemes
            }

            
        return {"status": "error", "message": f"N8N error: {response.status_code}"}
        
    except Exception as e:
        return {"status": "error", "message": str(e)}