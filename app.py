import os
import csv
import uuid
import json
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from qdrant_client import QdrantClient
from qdrant_client.models import VectorParams, Distance, PointStruct
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


def trim(text, limit=600):
    """Lambe text fields ko safe length tak trim karta hai taaki Groq prompt size control me rahe."""
    text = text or "N/A"
    text = str(text)
    return text[:limit] + ("..." if len(text) > limit else "")


@app.get("/")
def home():
    return {"message": "Backend is running permanently without n8n!"}


# ⚠️ TEMPORARY MIGRATION ENDPOINT — kaam ho jaane ke baad ye pura block hata dena!
# Ye CSV ko sahi structured format me Qdrant ki nayi collection me upload karta hai.
MIGRATION_SECRET = os.getenv("MIGRATION_SECRET", "change-this-secret-123")


@app.get("/admin/reupload-schemes")
def reupload_schemes(secret: str = ""):
    if secret != MIGRATION_SECRET:
        raise HTTPException(status_code=403, detail="Invalid secret")

    csv_path = os.path.join(os.path.dirname(__file__), "merged_schemes.csv")
    if not os.path.exists(csv_path):
        raise HTTPException(status_code=404, detail=f"CSV not found at {csv_path}")

    collection_name = "government_schemes_v2"
    vector_size = 768

    # Naya collection banao (agar pehle se hai to delete karke fresh banayenge)
    if qdrant_client.collection_exists(collection_name):
        qdrant_client.delete_collection(collection_name)

    qdrant_client.create_collection(
        collection_name=collection_name,
        vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
    )

    points = []
    skipped = 0

    with open(csv_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            scheme_name = (row.get("scheme_name") or "").strip()
            if not scheme_name:
                skipped += 1
                continue

            payload = {
                "scheme_name": scheme_name,
                "slug": (row.get("slug") or "").strip(),
                "details": (row.get("details") or "").strip(),
                "benefits": (row.get("benefits") or "").strip(),
                "eligibility": (row.get("eligibility") or "").strip(),
                "application": (row.get("application") or "").strip(),
                "documents": (row.get("documents") or "").strip(),
                "level": (row.get("level") or "").strip(),
                "beneficiaryState": (row.get("beneficiaryState") or "").strip(),
                "schemeCategory": (row.get("schemeCategory") or "").strip(),
                "nodalMinistryName": (row.get("nodalMinistryName") or "").strip(),
                "tags": (row.get("tags") or "").strip(),
            }

            points.append(
                PointStruct(
                    id=str(uuid.uuid4()),
                    vector=[0.0] * vector_size,
                    payload=payload,
                )
            )

    batch_size = 200
    for i in range(0, len(points), batch_size):
        batch = points[i:i + batch_size]
        qdrant_client.upsert(collection_name=collection_name, points=batch)

    info = qdrant_client.get_collection(collection_name)
    sample = qdrant_client.scroll(collection_name=collection_name, limit=1, with_payload=True)[0]
    sample_payload = sample[0].payload if sample else None

    return {
        "status": "success",
        "collection": collection_name,
        "total_rows_in_csv": len(points) + skipped,
        "uploaded_points": len(points),
        "skipped_empty_rows": skipped,
        "points_in_collection_now": info.points_count,
        "sample_payload": sample_payload,
    }
# ⚠️ TEMPORARY MIGRATION ENDPOINT ENDS HERE — kaam ho jaane ke baad ye pura block hata dena!


@app.post("/api/check-eligibility")
async def check_eligibility(profile: CitizenProfile):
    try:
        # 🧠 1. यूज़र की प्रोफाइल का एक टेक्स्ट प्रॉम्प्ट बनाएं
        user_query = (
            f"State: {profile.state}, Income: {profile.income}, "
            f"Category: {profile.category}, Occupation: {profile.occupation}, "
            f"Age: {profile.dob}, Gender: {profile.gender}"
        )

        # 🔍 2. Qdrant से सारी योजनाएं लाएं
        search_results = qdrant_client.scroll(
            collection_name="government_schemes_v2",
            limit=5000,
            with_payload=True
        )[0]

        # 🎯 3. Sirf relevant schemes filter karo: structured beneficiaryState field se
        relevant_schemes = []
        state_lower = (profile.state or "").lower().strip()

        for point in search_results:
            payload = point.payload
            beneficiary_state = (payload.get("beneficiaryState", "") or "").lower().strip()

            # "All" ka matlab har state ke liye applicable hai (Central schemes aksar aisi hoti hain)
            if beneficiary_state == "all":
                relevant_schemes.append(payload)
            elif state_lower and state_lower in beneficiary_state:
                relevant_schemes.append(payload)

        # Groq token limit ke andar rehne ke liye top 20 tak limit karo
        relevant_schemes = relevant_schemes[:20]

        print(f"Total schemes fetched from Qdrant: {len(search_results)}")
        print(f"Relevant schemes after filtering: {len(relevant_schemes)}")

        # Agar koi bhi relevant scheme na mile, Groq ko call karne ki zaroorat nahi
        if not relevant_schemes:
            return {
                "status": "success",
                "schemes": [],
                "message": "No matching schemes found for this profile."
            }

        # 📝 4. Schemes ka trimmed text banao
        schemes_text = ""
        for payload in relevant_schemes:
            schemes_text += (
                f"Scheme Name: {payload.get('scheme_name', 'N/A')}\n"
                f"Description: {trim(payload.get('details'), 400)}\n"
                f"Eligibility Criteria: {trim(payload.get('eligibility'), 300)}\n"
                f"Benefits: {trim(payload.get('benefits'), 300)}\n"
                f"Application Process: {trim(payload.get('application'), 500)}\n"
                f"Required Documents: {trim(payload.get('documents'), 300)}\n\n"
            )

        print(f"Prompt length (chars): {len(schemes_text)}")

        # 🤖 5. Groq AI को कॉल करें
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
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Citizen Profile:\n{user_query}\n\nAvailable Schemes:\n{schemes_text}"}
            ],
            temperature=0.2,
            max_tokens=4000
        )

        finish_reason = response.choices[0].finish_reason
        ai_output = (response.choices[0].message.content or "").strip()

        print(f"Finish reason: {finish_reason}")
        print(f"Raw output length: {len(ai_output)}")
        print(f"RAW GROQ OUTPUT (first 2000 chars): {ai_output[:2000]}")

        if not ai_output:
            raise HTTPException(
                status_code=500,
                detail=f"Groq returned an empty response. Finish reason: {finish_reason}"
            )

        # मार्कडाउन फ़ेंस साफ़ करें अगर एआई ने लगा दिया हो
        if ai_output.startswith("```"):
            ai_output = ai_output.replace("```json", "").replace("```", "").strip()

        try:
            parsed_json = json.loads(ai_output)
        except json.JSONDecodeError as je:
            print(f"JSON parse failed. Raw output was: {ai_output}")
            raise HTTPException(
                status_code=500,
                detail=f"Groq returned invalid JSON: {str(je)}"
            )

        final_schemes = parsed_json.get("schemes", [])

        return {
            "status": "success",
            "schemes": final_schemes
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error occurred: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    # यह रेंडर के एनवायरनमेंट से $PORT खींचेगा, अगर नहीं मिला तो डिफ़ॉल्ट 10000 यूज़ करेगा
    port = int(os.getenv("PORT", 10000))
    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=False)
