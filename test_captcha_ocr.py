"""
Test CAPTCHA OCR reading with Tesseract
This script tests if we can automatically solve CAPTCHAs using OCR
"""

import base64
import io
from PIL import Image
import pytesseract
import sys
import os

def test_ocr_on_captcha_base64(captcha_base64, captcha_name="test_captcha.png"):
    """
    Test OCR on a base64-encoded CAPTCHA image
    
    Args:
        captcha_base64: Base64 string (without "data:image/png;base64," prefix)
        captcha_name: Name for logging
    
    Returns:
        dict with OCR results
    """
    try:
        # Decode base64 to image
        image_data = base64.b64decode(captcha_base64)
        image = Image.open(io.BytesIO(image_data))
        
        # Try basic OCR
        ocr_text = pytesseract.image_to_string(image)
        
        # Clean up text (remove special chars, whitespace)
        cleaned_text = ''.join(c for c in ocr_text if c.isalnum()).strip()
        
        # Try with preprocessing (contrast enhancement for better OCR)
        image_enhanced = image.convert('RGB')
        ocr_text_enhanced = pytesseract.image_to_string(image_enhanced)
        cleaned_text_enhanced = ''.join(c for c in ocr_text_enhanced if c.isalnum()).strip()
        
        print(f"📋 OCR Results for {captcha_name}:")
        print(f"  Raw OCR:      '{ocr_text.strip()}'")
        print(f"  Cleaned:      '{cleaned_text}'")
        print(f"  Enhanced:     '{ocr_text_enhanced.strip()}'")
        print(f"  Cleaned Enh:  '{cleaned_text_enhanced}'")
        print()
        
        return {
            "raw": ocr_text.strip(),
            "cleaned": cleaned_text,
            "enhanced": cleaned_text_enhanced,
            "success": len(cleaned_text) > 0
        }
        
    except Exception as e:
        print(f"❌ Error processing {captcha_name}: {e}")
        return {"error": str(e), "success": False}


def analyze_captcha_difficulty(image_path):
    """Analyze how difficult a CAPTCHA image is for OCR"""
    try:
        image = Image.open(image_path)
        print(f"📊 Image Analysis: {image_path}")
        print(f"  Size: {image.size}")
        print(f"  Mode: {image.mode}")
        print(f"  Format: {image.format}")
        
        # Try Tesseract config options
        configs = [
            (pytesseract.image_to_string(image), "Default"),
            (pytesseract.image_to_string(image, config='--psm 8'), "PSM 8 (single word)"),
            (pytesseract.image_to_string(image, config='--psm 6'), "PSM 6 (single block)"),
            (pytesseract.image_to_string(image, config='--oem 3 -l eng'), "OEM 3 (legacy+LSTM)"),
        ]
        
        print("\n  OCR Attempts:")
        for text, method in configs:
            cleaned = ''.join(c for c in text if c.isalnum()).strip()
            print(f"    {method:20} → '{cleaned}'")
        
        print()
        
    except Exception as e:
        print(f"❌ Error analyzing {image_path}: {e}")


if __name__ == "__main__":
    print("=" * 60)
    print("🔍 CAPTCHA OCR Testing")
    print("=" * 60)
    print()
    
    # Check if there are any saved CAPTCHA images
    import glob
    
    captcha_files = glob.glob("/Volumes/algsoch/sachin/Kairon/backend/captcha_*.png")
    
    if captcha_files:
        print(f"Found {len(captcha_files)} CAPTCHA images to test:")
        for captcha_file in captcha_files[:3]:  # Test first 3
            print(f"\n📁 Testing: {captcha_file}")
            analyze_captcha_difficulty(captcha_file)
    else:
        print("⚠️  No CAPTCHA images found. Run login to capture one.")
        print("\nTo capture a CAPTCHA:")
        print("  1. Start the server: .venv/bin/python backend/app.py")
        print("  2. Visit http://127.0.0.1:5000/")
        print("  3. Enter roll no, password, semester")
        print("  4. Click 'Connect to Portal'")
        print("  5. CAPTCHA image will be displayed")
        print("\nTo test OCR, call this script again after capturing a CAPTCHA.")
        sys.exit(1)
    
    print("\n" + "=" * 60)
    print("📈 Recommendations:")
    print("=" * 60)
    print("""
If OCR can read CAPTCHA with >70% accuracy:
  ✓ We can AUTOMATE CAPTCHA solving
  ✓ User won't need to manually enter it
  ✓ Completely seamless login!

If OCR accuracy is low (<50%):
  ~ Manual entry or advanced OCR services needed
  ~ Consider: Google Cloud Vision, Azure Computer Vision
  ~ Or: Use OCR service API with higher accuracy
    """)
