// Where this page finds the BrandMaestro API.
//
// Empty: the API is at the same address as this page. That is the case when
// the FastAPI backend serves static/ itself (local development, Docker).
//
// When the UI is hosted on its own (e.g. on Vercel), set this to the
// backend's public URL, e.g. "https://api.example.com", and add the UI's
// address to FRONTEND_URL in the backend's .env so CORS allows it.
window.BRANDMAESTRO_API_BASE = "";
