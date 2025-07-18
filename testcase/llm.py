from google import genai
from google.genai import types
import os

key = os.getenv("GEMINI_API_KEY") 
def call_gemini(user_prompt: str, system_prompt=None, response_format=None, response_schema=None):
    client = genai.Client(
        api_key=key
    )

    model = "gemini-2.5-pro-preview-06-05"
    contents = [
        types.Content(
            role="user",
            parts=[types.Part.from_text(text=user_prompt)],
        ),
    ]

    generate_content_config = types.GenerateContentConfig(
        system_instruction=system_prompt,
        response_mime_type=response_format,
        response_schema=response_schema,
    )

    response = client.models.generate_content(
                model=model,
                config=generate_content_config,
                contents=contents,
            )
    return response.text

def get_context_limit(model = "gemini-2.5-pro-preview-06-05"):
    client = genai.Client(api_key=key)
    model_info = client.models.get(model=model)
    return (model_info.input_token_limit, model_info.output_token_limit)

def count_tokens(prompt: str, model = "gemini-2.5-pro-preview-06-05"):
    client = genai.Client(api_key=key)
    total_tokens = client.models.count_tokens(
        model=model, contents=prompt
    )
    return total_tokens