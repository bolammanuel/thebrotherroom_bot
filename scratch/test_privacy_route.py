import sys
from dashboard import app

client = app.test_client()

# Test landing page GET
res_landing = client.get("/")
print("Landing route status:", res_landing.status_code)
assert res_landing.status_code == 200
assert "Data Privacy Policy" in res_landing.get_data(as_text=True)
assert "YOUR DATA PRIVACY IS PROTECTED" in res_landing.get_data(as_text=True)

# Test /privacy route GET
res_privacy = client.get("/privacy")
print("/privacy route status:", res_privacy.status_code)
assert res_privacy.status_code == 200
assert "YouthHubAfrica Data Privacy Policy" in res_privacy.get_data(as_text=True)

# Test /data-privacy-policy route GET
res_data_privacy = client.get("/data-privacy-policy")
print("/data-privacy-policy route status:", res_data_privacy.status_code)
assert res_data_privacy.status_code == 200
assert "YouthHubAfrica Data Privacy Policy" in res_data_privacy.get_data(as_text=True)

print("ALL PRIVACY POLICY ROUTE TESTS PASSED SUCCESSFULLY!")
