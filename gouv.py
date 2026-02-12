import pandas as pd
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
from bs4 import BeautifulSoup
import time
import re
from urllib.parse import quote # Import for URL encoding

# --- Configuration ---
BASE_URL = "http://197.13.14.115:90"
# --- Define the Governorate to scrape ---
GOVERNORATE_TO_SCRAPE = "Bizerte" # <<< CHANGE THIS VALUE FOR DIFFERENT GOVERNORATES
# GOVERNORATE_TO_SCRAPE = "Tunis"
# GOVERNORATE_TO_SCRAPE = "Sousse"
# etc.

# URL-encode the governorate name for safety
ENCODED_GOVERNORATE = quote(GOVERNORATE_TO_SCRAPE)
START_URL = f"{BASE_URL}/AnnuairesMedecins/IndexAnnuairesMedecins?ville={ENCODED_GOVERNORATE}"

# Generate output filename based on governorate
OUTPUT_CSV = f"{GOVERNORATE_TO_SCRAPE.replace(' ', '_')}_doctors.csv"

# Selectors (Seem okay based on previous structure and DevExpress common patterns)
TABLE_SELECTOR = "#MedecinNPGSGridView_DXMainTable"
DATA_ROW_SELECTOR = "tr.dxgvDataRow_MetropolisBlue"
CELL_SELECTOR = "td.dxgv"
PAGER_SELECTOR = "#MedecinNPGSGridView_DXPagerBottom"
NEXT_BUTTON_LINK_SELECTOR = f"{PAGER_SELECTOR} a.dxp-button:has(img[alt='Next'])" # Target Next within Pager
PAGER_SUMMARY_SELECTOR = f"{PAGER_SELECTOR} b.dxp-summary"
LOADING_PANEL_SELECTOR = "#MedecinNPGSGridView_LP" # Useful for waiting potentially

# --- Main Scraping Logic ---
def scrape_doctors(start_url, governorate_name):
    """
    Scrapes doctor data for a specific governorate.

    Args:
        start_url (str): The initial URL for the governorate search results.
        governorate_name (str): The name of the governorate being scraped.

    Returns:
        list: A list of dictionaries, each containing data for one doctor.
    """
    all_doctors_data = []
    current_page_text = "" # Track pager text to detect page changes

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False) # Set to True for production runs
        page = browser.new_page()
        # Use a common user agent
        page.set_extra_http_headers({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36"})

        print(f"Navigating to initial URL for {governorate_name}: {start_url}")
        try:
            page.goto(start_url, wait_until='domcontentloaded', timeout=60000) # Try domcontentloaded first
            print("Initial page navigation likely finished (DOM loaded).")
            # Add a small wait for dynamic content if needed after DOM load
            time.sleep(3)
        except Exception as e:
            print(f"Error during initial navigation to {start_url}: {e}")
            try: page.screenshot(path=f"screenshot_{governorate_name}_initial_load_error.png")
            except: pass
            browser.close()
            return []

        page_count = 1
        while True:
            print(f"--- Scraping Page {page_count} for {governorate_name} ---")

            # --- Wait for Table (Essential) ---
            try:
                print("Waiting for table to be visible...")
                page.wait_for_selector(TABLE_SELECTOR, state='visible', timeout=45000)
                print("Table is visible.")
                # Wait slightly longer AFTER table is visible for rows to potentially render
                time.sleep(3)
            except Exception as e:
                 print(f"Error: Could not find or wait for table on page {page_count}: {e}")
                 try: page.screenshot(path=f"screenshot_{governorate_name}_page_{page_count}_table_error.png")
                 except: pass
                 break

            # --- Get Current Pager State (for change detection later) ---
            current_page_text = "" # Reset for each page
            try:
                if page.locator(PAGER_SUMMARY_SELECTOR).is_visible(timeout=5000):
                    current_page_text = page.locator(PAGER_SUMMARY_SELECTOR).text_content(timeout=5000)
                    print(f"Current Pager Text: {current_page_text}")
                else:
                    print("Pager summary not found or not visible.")
            except Exception as e:
                print(f"Warning: Could not get current pager text: {e}")


            # --- Extract Data ---
            try:
                table_html = page.locator(TABLE_SELECTOR).inner_html(timeout=20000)
                soup = BeautifulSoup(table_html, 'html.parser')
                rows = soup.select(DATA_ROW_SELECTOR)
                print(f"Found {len(rows)} data rows on this page.")

                if not rows and page_count > 1:
                     print("No data rows found after page change. Assuming end of data.")
                     break # Stop if table becomes empty on subsequent pages
                elif not rows and page_count == 1:
                     print("No data rows found on the first page. Check selectors or if results exist for this governorate.")
                     try: page.screenshot(path=f"screenshot_{governorate_name}_page_{page_count}_no_rows.png")
                     except: pass
                     break

                for row_index, row in enumerate(rows):
                    cells = row.select(CELL_SELECTOR)
                    # Expecting 5 columns: Name, Specialty, Mode, Address, Phone
                    if len(cells) >= 5:
                        # Strip whitespace and replace non-breaking spaces
                        doc_name = cells[0].get_text(strip=True).replace('\xa0', ' ').strip()
                        specialty = cells[1].get_text(strip=True).replace('\xa0', ' ').strip()
                        mode = cells[2].get_text(strip=True).replace('\xa0', ' ').strip()
                        address = cells[3].get_text(strip=True).replace('\xa0', ' ').strip()
                        phone = cells[4].get_text(strip=True).replace('\xa0', '').strip() # Remove space for phone

                        doctor_info = {
                            "Nom & Prénom": doc_name,
                            "Spécialité": specialty, # Keep specialty as it's in the table
                            "Mode Exercice": mode,
                            "Adresse Professionnelle": address if address else "", # Handle empty cells
                            "Téléphone": phone if phone else "",
                            "Governorate": governorate_name # Add the governorate
                        }
                        all_doctors_data.append(doctor_info)
                    else:
                         print(f"Warning: Row {row_index+1} skipped, expected 5+ cells, found {len(cells)}")

            except Exception as e:
                print(f"Error extracting data from table on page {page_count}: {e}")
                try: page.screenshot(path=f"screenshot_{governorate_name}_page_{page_count}_extract_error.png")
                except: pass
                break


            # --- Pagination Logic ---
            try:
                next_button_link = page.locator(NEXT_BUTTON_LINK_SELECTOR)

                # Check if the Next button exists AND is not disabled (check class or presence of enabled style)
                # Using is_visible/is_enabled is generally reliable for DevExpress
                is_visible = next_button_link.is_visible(timeout=5000)
                is_enabled = next_button_link.is_enabled(timeout=5000) if is_visible else False

                if is_visible and is_enabled:
                    print("Next button found and enabled. Clicking...")

                    # --- Click and Wait for Page Update ---
                    next_button_link.click(timeout=20000)
                    print("Clicked Next. Waiting for potential update...")

                    # Wait strategy: Primarily wait for the pager text to change. Fallback if it doesn't.
                    try:
                        if current_page_text: # Only wait if we got the initial text
                            page.wait_for_function(f"""
                                (expectedText) => {{
                                    const element = document.querySelector('{PAGER_SUMMARY_SELECTOR}');
                                    // Compare only the 'Page X of Y' part, ignore total items if it fluctuates
                                    const currentText = element ? element.textContent.split('(')[0].trim() : '';
                                    return element && currentText !== expectedText;
                                }}
                            """, arg=current_page_text.split('(')[0].strip(), timeout=30000)
                            new_page_text = page.locator(PAGER_SUMMARY_SELECTOR).text_content(timeout=5000)
                            print(f"Pager text updated to: {new_page_text}")
                        else:
                            # If no initial pager text, use a less precise wait
                            print("No initial pager text, using network idle wait.")
                            page.wait_for_load_state('networkidle', timeout=25000)

                    except PlaywrightTimeoutError:
                        print("Warning: Pager text did not change or update wait timed out. Content might be loaded anyway or stuck.")
                        # Force a small sleep as a final fallback before next loop iteration
                        time.sleep(4)
                    except Exception as wait_err:
                         print(f"Error during custom wait function: {wait_err}. Using network idle fallback.")
                         page.wait_for_load_state('networkidle', timeout=25000) # Wait for network activity to stop


                    page_count += 1 # Increment page count only if Next was successfully processed

                else:
                    print("Next button not visible or not enabled. Assuming last page.")
                    break # Exit loop

            except PlaywrightTimeoutError:
                 print("Next button check timed out (not found/visible/enabled quickly). Assuming last page.")
                 break
            except Exception as e:
                print(f"Error during pagination check/click on page {page_count}: {e}")
                try: page.screenshot(path=f"screenshot_{governorate_name}_page_{page_count}_pagination_error.png")
                except: pass
                break

        print(f"Finished scraping for {governorate_name}. Total doctors found: {len(all_doctors_data)}")
        browser.close()
        return all_doctors_data

# --- Execution ---
if __name__ == "__main__":
    print(f"--- Starting scrape for Governorate: {GOVERNORATE_TO_SCRAPE} ---")
    print(f"Target URL structure: {START_URL}")
    print(f"Output file: {OUTPUT_CSV}")

    scraped_data = scrape_doctors(START_URL, GOVERNORATE_TO_SCRAPE)

    if scraped_data:
        df = pd.DataFrame(scraped_data)
        # Clean up potential empty strings resulting from stripping ' ' etc.
        df = df.replace(r'^\s*$', '', regex=True)
        # Ensure correct column order if needed, Governorate will be last by default
        # df = df[["Nom & Prénom", "Spécialité", "Mode Exercice", "Adresse Professionnelle", "Téléphone", "Governorate"]]
        df.to_csv(OUTPUT_CSV, index=False, encoding='utf-8-sig') # Use utf-8-sig for Excel compatibility
        print(f"Data successfully saved to {OUTPUT_CSV}")
    else:
        print(f"No data was scraped for {GOVERNORATE_TO_SCRAPE}.")