## SlideTalk

SlideTalk is a simple Streamlit app that turns slide images into:

- a Korean presentation script
- estimated speaking time
- optional generated audio

### Setup

1. Create a virtual environment and install dependencies.
2. For local Streamlit use, create `.streamlit/secrets.toml`.
3. Add:

```toml
KANANA_BASE_URL = "https://kanana-o.a2s-endpoint.kr-central-2.kakaocloud.com/v1"
KANANA_MODEL = "kanana-o"
KANANA_API_KEY = "your-api-key"
```

4. Run the app:

```bash
streamlit run app.py
```

### Project Structure

```text
.
├── app.py
├── requirements.txt
└── slidetalk
    ├── config.py
    ├── models.py
    ├── prompts.py
    ├── services.py
    └── ui.py
```

### Notes

- Uploaded slides are processed in the order they are added in the UI.
- Audio generation depends on the provider returning streamed audio chunks.
- Streamlit secrets are used first.
- For Streamlit Community Cloud deployment, set the same keys in the app Secrets settings.
- Environment variables and `.env` are fallback options for non-Streamlit local runs.
