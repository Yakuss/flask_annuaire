import pandas as pd
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
from bs4 import BeautifulSoup
import time
import re

# --- Configuration ---
BASE_URL = "http://197.13.14.115:90"
SPECIALTY_GUID = "32c20d96-f256-42da-8591-3b5787ee35a0" 
START_URL = f"{BASE_URL}/AnnuairesMedecins/IndexAnnuairesMedecins?strGuidSpecialite=value{SPECIALTY_GUID}"
OUTPUT_CSV = "Gastro-entirologie.csv"

# Selectors
TABLE_SELECTOR = "#MedecinNPGSGridView_DXMainTable"
DATA_ROW_SELECTOR = "tr.dxgvDataRow_MetropolisBlue"
CELL_SELECTOR = "td.dxgv"
PAGER_SELECTOR = "#MedecinNPGSGridView_DXPagerBottom" # Keep selector for pager text if needed
NEXT_BUTTON_LINK_SELECTOR = "a.dxp-button:has(img[alt='Next'])"
PAGER_SUMMARY_SELECTOR = f"{PAGER_SELECTOR} b.dxp-summary" # Keep for logging if visible
LOADING_PANEL_SELECTOR = "#MedecinNPGSGridView_LP"

# --- Main Scraping Logic ---
def scrape_doctors():
    all_doctors_data = []
    current_page_text = ""

    with sync_playwright() as p:
        # browser = p.chromium.launch(headless=True)
        browser = p.chromium.launch(headless=False) # Keep False for now
        page = browser.new_page()
        page.set_extra_http_headers({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36"})

        print(f"Navigating to initial URL: {START_URL}")
        try:
            page.goto(START_URL, wait_until='load', timeout=60000)
            print("Initial page navigation finished.")
        except Exception as e:
            print(f"Error during initial navigation: {e}")
            # Attempt screenshot before closing
            try: page.screenshot(path="screenshot_initial_load_error.png")
            except: pass
            browser.close()
            return []

        page_count = 1
        while True:
            print(f"--- Scraping Page {page_count} ---")

            # --- Wait for Table (Essential) ---
            try:
                print("Waiting for table to be visible...")
                page.wait_for_selector(TABLE_SELECTOR, state='visible', timeout=60000)
                print("Table is visible.")
                time.sleep(2) # Small explicit wait after table appears
            except Exception as e:
                 print(f"Error: Could not find or wait for table on page {page_count}: {e}")
                 # Attempt screenshot
                 try: page.screenshot(path=f"screenshot_page_{page_count}_table_error.png")
                 except: pass
                 break # Cannot proceed without the table

            # --- Check Pager Visibility (Optional Logging) ---
            try:
                # Check if pager is visible without waiting long or causing an error
                if page.locator(PAGER_SELECTOR).is_visible(timeout=1000): # Short timeout check
                    print("Pager is visible.")
                    current_page_text = page.locator(PAGER_SUMMARY_SELECTOR).text_content(timeout=5000)
                    print(f"Current Pager Text: {current_page_text}")
                else:
                    print("Pager is not visible (or hidden). Assuming single page or will check Next button.")
                    # Assign a placeholder page text if pager isn't visible
                    current_page_text = f"Page {page_count} (Pager Hidden)"
            except Exception as e:
                print(f"Warning: Issue checking pager visibility or getting text: {e}")
                current_page_text = f"Page {page_count} (Pager Check Error)"


            # --- Extract Data ---
            try:
                table_html = page.locator(TABLE_SELECTOR).inner_html(timeout=15000)
                soup = BeautifulSoup(table_html, 'html.parser')
                rows = soup.select(DATA_ROW_SELECTOR)
                print(f"Found {len(rows)} data rows on this page.")

                if not rows:
                     print("No data rows found in the table.")
                     if page_count == 1:
                         print("Problem finding rows on the very first page. Check selectors or page content.")
                         try: page.screenshot(path=f"screenshot_page_{page_count}_no_rows.png")
                         except: pass
                     else:
                          print("Assuming end of data after page change.")
                     break # Stop if table is empty

                for row in rows:
                    cells = row.select(CELL_SELECTOR)
                    if len(cells) >= 5:
                        doc_name = cells[0].get_text(strip=True).replace('\xa0', ' ')
                        specialty = cells[1].get_text(strip=True).replace('\xa0', ' ')
                        mode = cells[2].get_text(strip=True).replace('\xa0', ' ')
                        address = cells[3].get_text(strip=True).replace('\xa0', ' ')
                        phone = cells[4].get_text(strip=True).replace('\xa0', '')

                        doctor_info = {
                            "Nom & Prénom": doc_name,
                            "Spécialité": specialty,
                            "Mode Exercice": mode,
                            "Adresse Professionnelle": address if address else "",
                            "Téléphone": phone if phone else ""
                        }
                        all_doctors_data.append(doctor_info)
                    else:
                         print(f"Warning: Row skipped, expected 5+ cells, found {len(cells)}")

            except Exception as e:
                print(f"Error extracting data from table on page {page_count}: {e}")
                try: page.screenshot(path=f"screenshot_page_{page_count}_extract_error.png")
                except: pass
                # Decide whether to break or continue
                break


            # --- Pagination Check (Based ONLY on Next Button) ---
            try:
                next_button_link = page.locator(NEXT_BUTTON_LINK_SELECTOR)

                # Check if the Next button exists AND is clickable (visible and enabled)
                # Use a short timeout as we don't expect it to appear dynamically *after* table load
                if next_button_link.is_visible(timeout=3000) and next_button_link.is_enabled(timeout=3000):
                    print("Next button found and enabled. Proceeding to click...")
                    next_button_link.click(timeout=15000)

                    # --- Wait for update (Crucial: Use pager text change if possible, or fallback) ---
                    print(f"Waiting for page content to update...")
                    try:
                        # Primary wait: check if pager summary text changes
                        page.wait_for_function(f"""
                            (expectedText) => {{
                                const element = document.querySelector('{PAGER_SUMMARY_SELECTOR}');
                                return element && element.textContent !== expectedText;
                            }}
                        """, arg=current_page_text.split('(')[0].strip(), timeout=30000) # Compare only the core "Page X of Y" part
                        new_page_text = page.locator(PAGER_SUMMARY_SELECTOR).text_content(timeout=5000)
                        print(f"Pager text updated to: {new_page_text}")
                    except PlaywrightTimeoutError:
                        print("Warning: Pager text did not change after clicking Next. Might be an issue or slow load.")
                        # Add a fallback wait - e.g., wait for network idle or a fixed time
                        print("Applying fallback wait (networkidle)...")
                        page.wait_for_load_state('networkidle', timeout=20000) # Wait for activity to stop
                        # Or a simple sleep: time.sleep(5)
                    except Exception as wait_err:
                         print(f"Error during update wait function: {wait_err}. Applying fallback wait.")
                         page.wait_for_load_state('networkidle', timeout=20000) # Wait for activity to stop


                    page_count += 1 # Increment page count only if Next was clicked

                else:
                    print("Next button not visible or not enabled. Reached the last page.")
                    break # Exit loop, this was the last page

            except PlaywrightTimeoutError:
                 # This timeout usually means the next_button_link itself wasn't found/visible/enabled quickly
                 print("Next button check timed out or button not found. Assuming last page.")
                 break
            except Exception as e:
                print(f"Error during pagination check/click: {e}")
                try: page.screenshot(path=f"screenshot_page_{page_count}_pagination_error.png")
                except: pass
                break

        print(f"Finished scraping. Total doctors found: {len(all_doctors_data)}")
        browser.close()
        return all_doctors_data

# --- Execution ---
if __name__ == "__main__":
    scraped_data = scrape_doctors()

    if scraped_data:
        df = pd.DataFrame(scraped_data)
        df = df.replace(r'^\s*$', '', regex=True)
        df.to_csv(OUTPUT_CSV, index=False, encoding='utf-8-sig')
        print(f"Data successfully saved to {OUTPUT_CSV}")
    else:
        print("No data was scraped.")