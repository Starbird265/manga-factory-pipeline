import os
import sys

# Ensure we can import the new ML modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_smart_pipeline():
    try:
        from smart_pipeline_manager import SmartPipelineManager
        print("Testing SmartPipelineManager...")
        mgr = SmartPipelineManager(data_dir='/tmp')
        strat = mgr.get_strategy("https://example.com/manga")
        print(f"  Got strategy: {strat}")
        mgr.record_scraper_result("https://example.com/manga", "generic", True, 20)
        print("  ✅ SmartPipelineManager test passed")
    except Exception as e:
        print(f"  ❌ SmartPipelineManager test failed: {e}")

def test_ml_proxy():
    try:
        from ml_proxy_manager import MLProxyManager
        print("Testing MLProxyManager...")
        mgr = MLProxyManager(data_dir='/tmp')
        proxy = mgr.get_best_proxy()
        print(f"  Best proxy returned: {proxy}")
        if proxy:
            mgr.report_result(proxy, True, 250)
        print("  ✅ MLProxyManager test passed")
    except Exception as e:
        print(f"  ❌ MLProxyManager test failed: {e}")

def test_ml_site_learner():
    try:
        from ml_site_learner import MLSiteLearner
        print("Testing MLSiteLearner...")
        learner = MLSiteLearner()
        # Mock HTML
        html = '''
        <html>
            <body>
                 <div class="reading-content">
                      <img src="https://cdn.example.com/page1.jpg" data-src="https://cdn.example.com/page1.jpg"/>
                      <img class="wp-manga-chapter-img" src="https://cdn.example.com/page2.jpg"/>
                 </div>
            </body>
        </html>
        '''
        images = learner.analyze_dom_for_manga_images(html, "https://example.com/manga")
        print(f"  Found images: {images}")
        if len(images) == 2:
            print("  ✅ MLSiteLearner test passed")
        else:
            print("  ❌ MLSiteLearner test failed: did not find expected 2 images")
    except Exception as e:
        print(f"  ❌ MLSiteLearner test failed: {e}")

if __name__ == '__main__':
    print("--- Running ML Component Verification ---")
    test_smart_pipeline()
    test_ml_proxy()
    test_ml_site_learner()
    print("--- Done ---")
