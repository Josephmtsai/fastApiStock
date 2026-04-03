from fastapi import FastAPI

app = FastAPI(title='FastAPI Stock', version='0.1.0')


@app.get('/health')
def health_check() -> dict[str, str]:
    """Check API health status."""
    return {'status': 'ok'}
