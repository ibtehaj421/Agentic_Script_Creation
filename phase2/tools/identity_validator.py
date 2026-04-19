import os
import cv2

def identity_validator(character_name: str, character_image_path: str) -> bool:
    """
    MCP Tool: Validates character identity before face swap.
    Uses OpenCV Haar Cascades to ensure a valid face exists in the reference image.
    """
    if not os.path.exists(character_image_path):
        print(f"Validation Error: Image not found at {character_image_path}")
        return False
        
    # Load OpenCV pre-trained face detector
    face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
    
    # Read image and convert to grayscale
    img = cv2.imread(character_image_path)
    if img is None:
        return False
        
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    # Detect faces
    faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=4)
    
    # Valid if exactly one face is found (ideal for face swapping)
    if len(faces) == 1:
        return True
    elif len(faces) > 1:
        print(f"Validation Warning: Multiple faces detected for {character_name}")
        return False
    else:
        print(f"Validation Error: No faces detected for {character_name}")
        return False