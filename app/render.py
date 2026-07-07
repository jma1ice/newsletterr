import base64

from playwright.sync_api import sync_playwright

from app import state

def capture_chart_images_via_headless(schedule_id: int, base: str, theme: str) -> dict:
    url = f"{base}/scheduling/{schedule_id}/preview-page?schedule_id={schedule_id}"
    
    with state._RENDER_LOCK:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True, args=["--no-sandbox"])
            context = browser.new_context(
                viewport={"width": 1280, "height": 900},
                color_scheme="dark" if theme == "dark" else "light"
            )
            page = context.new_page()
            page.on("console", lambda msg: print(f"PAGE LOG: {msg.text}"))
            page.goto(url, wait_until="load")
            print(f"Loaded URL (before waiting): {page.url}")
            
            try:
                page.wait_for_function("typeof loadPreview === 'function'", timeout=30_000)
                page.evaluate("loadPreview()")
                page.wait_for_function("typeof Highcharts !== 'undefined' && Highcharts.charts && Highcharts.charts.filter(Boolean).length > 0", timeout=60_000)
                page.wait_for_timeout(2000)
            except Exception as e:
                print(f"Error waiting for charts to load: {e}")

            try:
                page.wait_for_function("typeof selectedItems !== 'undefined'", timeout=10_000)
                selected_items = page.evaluate("selectedItems || []")
            except Exception as e:
                print(f"selectedItems never defined or timeout: {e}")
                selected_items = []

            chart_images = {}
            
            for item in selected_items:
                if item.get('type') == 'graph':
                    chart_id = item.get('id')
                    chart_name = item.get('name', 'Chart')
                    
                    print(f"Processing chart: {chart_id}")
                    
                    try:
                        page.evaluate(f"""
                            (() => {{
                                const element = document.getElementById('{chart_id}');
                                if (element) {{
                                    element.classList.remove('d-none');
                                    element.style.display = 'block';
                                    element.style.visibility = 'visible';
                                    element.style.opacity = '1';
                                    element.style.position = 'static';
                                    element.style.zIndex = '1';
                                    
                                    let parent = element.parentElement;
                                    while (parent && parent !== document.body) {{
                                        parent.style.display = 'block';
                                        parent.style.visibility = 'visible';
                                        parent.style.opacity = '1';
                                        parent = parent.parentElement;
                                    }}
                                    
                                    console.log('Made element visible:', '{chart_id}');
                                    return true;
                                }}
                                return false;
                            }})()
                        """)
                        
                        page.wait_for_timeout(1000)
                        
                        is_visible = page.evaluate(f"""
                            (() => {{
                                const element = document.getElementById('{chart_id}');
                                if (!element) return false;
                                const rect = element.getBoundingClientRect();
                                return rect.width > 0 && rect.height > 0;
                            }})()
                        """)
                        
                        print(f"Element #{chart_id} visible after adjustment: {is_visible}")
                        
                        if is_visible:
                            chart_element = page.locator(f"#{chart_id}")
                            screenshot_bytes = chart_element.screenshot(type='png', timeout=10000)
                            
                            screenshot_b64 = base64.b64encode(screenshot_bytes).decode('utf-8')
                            data_url = f"data:image/png;base64,{screenshot_b64}"
                            
                            chart_images[chart_id] = {
                                'name': chart_name,
                                'dataUrl': data_url
                            }
                            
                            print(f"Successfully captured screenshot for chart: {chart_id}")
                        else:
                            print(f"Chart element #{chart_id} still not visible after adjustments")
                        
                    except Exception as e:
                        print(f"Error capturing screenshot for chart {chart_id}: {e}")

            context.close()
            browser.close()
            
            print(f"Total chart images captured: {len(chart_images)}")
            return chart_images
