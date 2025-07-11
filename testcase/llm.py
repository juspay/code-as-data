from google import genai
from google.genai import types

def call_gemini(user_prompt: str, system_prompt=None, response_format=None, response_schema=None):
    client = genai.Client(
        api_key=""
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