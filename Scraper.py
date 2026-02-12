import pandas as pd
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
from bs4 import BeautifulSoup
import time
import re

# --- Configuration ---
# Base URL for the page with the dropdown
BASE_URL = "http://197.13.14.115:90"
START_PAGE_URL = f"{BASE_URL}/AnnuairesMedecins/IndexAnnuairesMedecins" # URL of the page with the dropdown
OUTPUT_CSV = "tunisian_doctors_all_specialties.csv"

# Selectors
DROPDOWN_SELECTOR = "#GuidSpecialite"
TABLE_SELECTOR = "#MedecinNPGSGridView_DXMainTable"
DATA_ROW_SELECTOR = "tr.dxgvDataRow_MetropolisBlue"
CELL_SELECTOR = "td.dxgv"
PAGER_SELECTOR = "#MedecinNPGSGridView_DXPagerBottom"
NEXT_BUTTON_LINK_SELECTOR = "a.dxp-button:has(img[alt='Next'])"
PAGER_SUMMARY_SELECTOR = f"{PAGER_SELECTOR} b.dxp-summary"
LOADING_PANEL_SELECTOR = "#MedecinNPGSGridView_LP" # Optional

# --- Helper Function to Scrape Pages for Current View ---
def scrape_current_specialty_pages(page, specialty_name):
    """Scrapes all pages for the currently selected specialty."""
    specialty_doctors_data = []
    page_count = 1
    initial_load = True # Flag for first page load of a specialty

    while True:
        print(f"--- Scraping Page {page_count} for Specialty: '{specialty_name}' ---")

        # --- Wait for Table (Essential) ---
        try:
            if not initial_load: # Don't wait excessively after the first page load triggered by select_option
                 print("Waiting for table update after pagination...")
                 # Use a slightly shorter timeout after pagination clicks
                 page.wait_for_selector(TABLE_SELECTOR, state='visible', timeout=30000)
            else:
                 print("Waiting for table after specialty selection...")
                 page.wait_for_selector(TABLE_SELECTOR, state='visible', timeout=60000) # Longer timeout for initial specialty load
            print("Table is visible.")
            time.sleep(2) # Small explicit wait
        except Exception as e:
             print(f"Error: Could not find or wait for table on page {page_count} for {specialty_name}: {e}")
             try: page.screenshot(path=f"screenshot_{specialty_name}_page_{page_count}_table_error.png")
             except: pass
             return specialty_doctors_data # Return whatever was collected so far for this specialty

        # Reset flag after first successful page load for this specialty
        initial_load = False

        # --- Get Pager Info (Optional Logging) ---
        current_page_text = f"Page {page_count} (Pager Check Skipped/Hidden)" # Default
        try:
            if page.locator(PAGER_SELECTOR).is_visible(timeout=1000):
                print("Pager is visible.")
                current_page_text = page.locator(PAGER_SUMMARY_SELECTOR).text_content(timeout=5000)
                print(f"Current Pager Text: {current_page_text}")
            else:
                print("Pager is not visible (or hidden).")
        except Exception as e:
            print(f"Warning: Issue checking pager visibility or getting text: {e}")

        # --- Extract Data ---
        try:
            table_html = page.locator(TABLE_SELECTOR).inner_html(timeout=15000)
            soup = BeautifulSoup(table_html, 'html.parser')
            rows = soup.select(DATA_ROW_SELECTOR)
            print(f"Found {len(rows)} data rows on this page.")

            if not rows:
                 print("No data rows found in the table.")
                 if page_count == 1:
                     print(f"No doctors listed for specialty: {specialty_name}")
                 else:
                     print("Assuming end of data for this specialty.")
                 break # Exit pagination loop for this specialty

            for row in rows:
                cells = row.select(CELL_SELECTOR)
                if len(cells) >= 5:
                    doc_name = cells[0].get_text(strip=True).replace('\xa0', ' ')
                    # specialty_from_table = cells[1].get_text(strip=True).replace('\xa0', ' ') # Can use this or the one passed in
                    mode = cells[2].get_text(strip=True).replace('\xa0', ' ')
                    address = cells[3].get_text(strip=True).replace('\xa0', ' ')
                    phone = cells[4].get_text(strip=True).replace('\xa0', '')

                    doctor_info = {
                        # Add the specialty name passed to the function
                        "Specialite_Selectionnee": specialty_name,
                        "Nom & Prénom": doc_name,
                        # "Spécialité_Table": specialty_from_table, # Optional: if you want to compare
                        "Mode Exercice": mode,
                        "Adresse Professionnelle": address if address else "",
                        "Téléphone": phone if phone else ""
                    }
                    specialty_doctors_data.append(doctor_info)
                else:
                     print(f"Warning: Row skipped, expected 5+ cells, found {len(cells)}")

        except Exception as e:
            print(f"Error extracting data from table on page {page_count} for {specialty_name}: {e}")
            try: page.screenshot(path=f"screenshot_{specialty_name}_page_{page_count}_extract_error.png")
            except: pass
            break # Exit pagination loop for this specialty on error


        # --- Pagination Check ---
        try:
            next_button_link = page.locator(NEXT_BUTTON_LINK_SELECTOR)
            if next_button_link.is_visible(timeout=3000) and next_button_link.is_enabled(timeout=3000):
                print("Next button found and enabled. Proceeding to click...")
                next_button_link.click(timeout=15000)

                # --- Wait for update ---
                print(f"Waiting for page content to update after pagination click...")
                try:
                    # Primary wait: Check for pager text change if pager was visible
                     if page.locator(PAGER_SELECTOR).is_visible(timeout=1000):
                           page.wait_for_function(f"""
                               (expectedText) => {{
                                   const element = document.querySelector('{PAGER_SUMMARY_SELECTOR}');
                                   // Check if element exists and text is different, handle initial state
                                   return element && element.textContent && element.textContent.split('(')[0].trim() !== '{current_page_text.split('(')[0].strip()}';
                               }}
                           """, timeout=30000)
                           new_page_text = page.locator(PAGER_SUMMARY_SELECTOR).text_content(timeout=5000)
                           print(f"Pager text updated to: {new_page_text}")
                     else:
                          # Fallback if pager wasn't visible: wait for network idle
                          print("Pager not visible, using network idle wait...")
                          page.wait_for_load_state('networkidle', timeout=25000)
                          print("Network idle after pagination click.")

                except PlaywrightTimeoutError:
                    print("Warning: Wait for update after Next click timed out. Assuming slow load or issue.")
                    # Apply a definite sleep as a last resort if other waits fail
                    time.sleep(5)
                except Exception as wait_err:
                    print(f"Error during update wait function: {wait_err}. Applying fallback wait.")
                    page.wait_for_load_state('networkidle', timeout=25000) # Fallback

                page_count += 1
            else:
                print("Next button not visible or not enabled. Reached the last page for this specialty.")
                break # Exit pagination loop

        except PlaywrightTimeoutError:
             print("Next button check timed out or button not found. Assuming last page for this specialty.")
             break
        except Exception as e:
            print(f"Error during pagination check/click for {specialty_name}: {e}")
            try: page.screenshot(path=f"screenshot_{specialty_name}_page_{page_count}_pagination_error.png")
            except: pass
            break # Exit pagination loop

    return specialty_doctors_data


# --- Main Scraping Function ---
def scrape_all_specialties():
    all_doctors_data = []

    with sync_playwright() as p:
        # browser = p.chromium.launch(headless=True)
        browser = p.chromium.launch(headless=False) # Start non-headless
        page = browser.new_page()
        page.set_extra_http_headers({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36"})

        print(f"Navigating to start page: {START_PAGE_URL}")
        try:
            page.goto(START_PAGE_URL, wait_until='load', timeout=60000)
            print("Start page navigation finished.")
            # Wait for the dropdown itself to be ready
            page.wait_for_selector(DROPDOWN_SELECTOR, state='visible', timeout=30000)
            print("Specialty dropdown is visible.")
        except Exception as e:
            print(f"FATAL: Error navigating to start page or finding dropdown: {e}")
            try: page.screenshot(path="screenshot_start_page_error.png")
            except: pass
            browser.close()
            return []

        # --- Get Specialties from Dropdown ---
        specialties = []
        try:
            print("Extracting specialties from dropdown...")
            options = page.locator(f"{DROPDOWN_SELECTOR} option")
            count = options.count()
            for i in range(count):
                option = options.nth(i)
                value = option.get_attribute('value')
                name = option.text_content()
                if value: # Skip the first empty option
                    # Clean up name (remove extra spaces/newlines)
                    cleaned_name = ' '.join(name.split())
                    specialties.append({'value': value, 'name': cleaned_name})
            print(f"Found {len(specialties)} specialties.")
        except Exception as e:
            print(f"FATAL: Could not extract specialties from dropdown: {e}")
            browser.close()
            return []

        if not specialties:
             print("FATAL: No specialties found in dropdown. Exiting.")
             browser.close()
             return []

        # --- Loop through each specialty ---
        for spec in specialties:
            guid = spec['value']
            name = spec['name']
            print(f"\n===== Selecting Specialty: {name} (GUID: {guid}) =====")

            try:
                # Select the option in the dropdown
                page.select_option(DROPDOWN_SELECTOR, value=guid)
                print(f"Selected '{name}'. Waiting for page update...")

                # Wait for the update - network idle is often reliable after selection change
                page.wait_for_load_state('networkidle', timeout=45000) # Increased timeout
                # Additional check: wait briefy for table to ensure it's present after load
                page.wait_for_selector(TABLE_SELECTOR, state='visible', timeout=10000)
                print("Page updated after specialty selection.")

                # Scrape all pages for this specialty using the helper function
                doctors_for_this_specialty = scrape_current_specialty_pages(page, name)
                print(f"Collected {len(doctors_for_this_specialty)} doctors for '{name}'.")
                all_doctors_data.extend(doctors_for_this_specialty) # Add to the main list

            except PlaywrightTimeoutError as time_err:
                 print(f"TIMEOUT ERROR processing specialty '{name}': {time_err}")
                 print("Skipping to next specialty.")
                 try: page.screenshot(path=f"screenshot_{name}_timeout_error.png")
                 except: pass
                 # Try navigating back to start page to reset state? Optional.
                 # try:
                 #    page.goto(START_PAGE_URL, wait_until='load', timeout=60000)
                 #    page.wait_for_selector(DROPDOWN_SELECTOR, state='visible', timeout=30000)
                 # except Exception as nav_err:
                 #    print(f"Could not navigate back to start page after error: {nav_err}")
                 #    break # Exit outer loop if we can't recover
                 continue # Go to the next specialty in the loop
            except Exception as e:
                print(f"ERROR processing specialty '{name}': {e}")
                print("Attempting to skip to next specialty.")
                try: page.screenshot(path=f"screenshot_{name}_processing_error.png")
                except: pass
                # Consider adding recovery logic here if needed
                continue # Go to the next specialty


        print(f"\nFinished scraping all specialties. Total doctors found: {len(all_doctors_data)}")
        browser.close()
        return all_doctors_data

# --- Execution ---
if __name__ == "__main__":
    scraped_data = scrape_all_specialties()

    if scraped_data:
        df = pd.DataFrame(scraped_data)
        df = df.replace(r'^\s*$', '', regex=True)
        # Reorder columns if desired
        try:
            df = df[["Specialite_Selectionnee", "Nom & Prénom", "Mode Exercice", "Adresse Professionnelle", "Téléphone"]]
        except KeyError:
            print("Warning: Could not reorder columns.") # In case a column name is mistyped

        df.to_csv(OUTPUT_CSV, index=False, encoding='utf-8-sig')
        print(f"Data successfully saved to {OUTPUT_CSV}")
    else:
        print("No data was scraped.")