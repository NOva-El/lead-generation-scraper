import requests
import re
import pandas as pd
import time
from concurrent.futures import ThreadPoolExecutor
import googlemaps
from bs4 import BeautifulSoup
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- ВСТАВЬ СЮДА СВОЙ API KEY ---
API_KEY = "API_KEY"
gmaps = googlemaps.Client(key=API_KEY)


# --- Получение координат города ---
def get_city_coordinates(city):
    try:
        res = gmaps.geocode(city)
        if not res:
            print(f"[-] City '{city}' not found.")
            return None, None
        location = res[0]["geometry"]["location"]
        return location["lat"], location["lng"]
    except Exception as e:
        print(f"[-] Geocoding error: {e}")
        return None, None


# --- Поиск компаний ---
def find_places(keyword, lat, lng):
    places_data = []
    visited = set()
    radius = 5000

    for dx in [-0.02, 0, 0.02]:
        for dy in [-0.02, 0, 0.02]:

            location = (lat + dx, lng + dy)

            try:
                response = gmaps.places_nearby(
                    location=location,
                    radius=radius,
                    keyword=keyword
                )

                page_count = 0

                while True:
                    page_count += 1

                    results = response.get("results", [])

                    for result in results:
                        pid = result.get("place_id")

                        # 🔥 ВАЖНО: фильтр ДО запроса details
                        if not pid or pid in visited:
                            continue

                        visited.add(pid)

                        try:
                            details = gmaps.place(
                                place_id=pid,
                                fields=["name", "website", "formatted_phone_number"]
                            )

                            item = details.get("result", {})

                            places_data.append({
                                "company": item.get("name"),
                                "website": item.get("website"),
                                "phone_maps": item.get("formatted_phone_number")
                            })

                        except Exception as e:
                            print(f"[-] Details error: {e}")

                    # --- ПАГИНАЦИЯ ---
                    token = response.get("next_page_token")

                    # ❗ защита от бесконечного цикла
                    if not token or page_count >= 3:
                        break

                    time.sleep(2)

                    response = gmaps.places_nearby(
                        page_token=token
                    )

            except Exception as e:
                print(f"[-] Search error: {e}")

    return places_data

                            # --- СКРЕЙПИНГ САЙТА ---
def scrape_site(item):
    if not item["website"]:
        return {**item, "emails": [], "phones_site": [], "instagram": None}

    emails, phones = set(), set()
    instagram = None

    headers = {"User-Agent": "Mozilla/5.0"}

    base_url = item["website"]
    if not base_url.startswith("http"):
        base_url = "https://" + base_url

    urls_to_check = [
        base_url,
        base_url + "/contact",
        base_url + "/kontakt",
        base_url + "/about"
    ]

    for url in urls_to_check:
        try:
            resp = requests.get(url, headers=headers, timeout=8, verify=False)
            if resp.status_code != 200:
                continue

            # --- EMAIL ---
            found_emails = re.findall(
                r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
                resp.text
            )

            for e in found_emails:
                e = e.lower()
                if not any(bad in e for bad in [
                    "example", "test", "noreply", "no-reply",
                    ".png", ".jpg", ".jpeg", ".svg"
                ]):
                    emails.add(e)

            soup = BeautifulSoup(resp.text, "html.parser")

            for a in soup.find_all("a", href=True):
                href = a["href"]

                # --- PHONE ---
                if href.startswith("tel:"):
                    clean = re.sub(r"[^\d+]", "", href.replace("tel:", ""))
                    if len(clean) > 6:
                        phones.add(clean)

                # --- INSTAGRAM ---
                if "instagram.com" in href and not instagram:
                    instagram = href.split("?")[0]

        except:
            continue

    time.sleep(0.5)

    return {
        **item,
        "emails": list(emails),
        "phones_site": list(phones),
        "instagram": instagram
    }


# --- MAIN ---
def main():
    city = input("Enter City (e.g. Oslo): ")
    biz = input("Enter Business Type (e.g. Beauty salon): ")

    lat, lng = get_city_coordinates(city)
    if not lat:
        return

    print(f"[*] Found coordinates: {lat}, {lng}. Searching...")
    raw_list = find_places(biz, lat, lng)
    print(f"[*] Found {len(raw_list)} companies. Scraping websites...")

    final_results = []

    with ThreadPoolExecutor(max_workers=10) as executor:
        for res in executor.map(scrape_site, raw_list):
            row = {
                "Company": res["company"],
                "Website": res["website"] if res["website"] else "No website",
                "Phone (Maps)": res["phone_maps"],
                "Emails": "; ".join(res["emails"]),
                "Phones (Site)": "; ".join(res["phones_site"]),
                "Instagram": res["instagram"] if res["instagram"] else ""
            }
            final_results.append(row)

    if final_results:
        df = pd.DataFrame(final_results)

        # Убираем дубликаты
        df.drop_duplicates(subset=["Company", "Website"], inplace=True)

        df.to_excel("leads_result.xlsx", index=False)

        print(f"\n[DONE] Saved {len(df)} companies to leads_result.xlsx")
    else:
        print("\n[-] Nothing found.")


if __name__ == "__main__":
    main()
