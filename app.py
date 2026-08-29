try:
    response = client.chat.completions.create(
        model=NEMOTRON_MODEL,
        messages=[
            {
                "role": "user",
                "content": prompt
            }
        ],
        temperature=0,
        max_tokens=8000,
        stream=False,
        extra_body={
            "chat_template_kwargs": {
                "enable_thinking": False
            }
        }
    )

except Exception as e:
    print("NVIDIA FULL ERROR:", repr(e))
    raise RuntimeError(
        f"NVIDIA API error: {e}"
    )
