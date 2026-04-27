import cv2
import mediapipe as mp
import math

class HandDetector:
    def __init__(self, mode=False, maxHands=2, detectionCon=0.5, trackCon=0.5):
        self.mode = mode
        self.maxHands = maxHands
        self.detectionCon = detectionCon
        self.trackCon = trackCon 

        self.mpHands = mp.solutions.hands
        self.hands = self.mpHands.Hands(
            static_image_mode=self.mode,
            max_num_hands=self.maxHands,
            min_detection_confidence=self.detectionCon,
            min_tracking_confidence=self.trackCon
        )
        self.mpDraw = mp.solutions.drawing_utils
        self.tipIds = [4, 8, 12, 16, 20]  # Thumb, Index, Middle, Ring, Pinky tips
        self.jointIds = [2, 6, 10, 14, 18]  # Thumb MCP, Index PIP, Middle PIP, Ring PIP, Pinky PIP

    def findHands(self, img, draw=True):
        imgRGB = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        self.results = self.hands.process(imgRGB)
        allHands = []
        h, w, c = img.shape

        if self.results.multi_hand_landmarks:  # Corrected typo: multi_hand_landmarks
            for handType, handLms in zip(self.results.multi_handedness, self.results.multi_hand_landmarks):
                myHand = {}
                lmList = []
                xList = []
                yList = []
                for id, lm in enumerate(handLms.landmark):
                    px, py = int(lm.x * w), int(lm.y * h)
                    lmList.append([px, py])
                    xList.append(px)
                    yList.append(py)

                xmin, xmax = min(xList), max(xList)
                ymin, ymax = min(yList), max(yList)
                boxW, boxH = xmax - xmin, ymax - ymin
                bbox = xmin, ymin, boxW, boxH
                cx, cy = bbox[0] + (bbox[2] // 2), bbox[1] + (bbox[3] // 2)

                myHand["lmList"] = lmList
                myHand["bbox"] = bbox
                myHand["center"] = (cx, cy)
                myHand["type"] = handType.classification[0].label

                if draw:
                    self.mpDraw.draw_landmarks(img, handLms, self.mpHands.HAND_CONNECTIONS)
                    # Draw landmark IDs for debugging
                    for id, lm in enumerate(handLms.landmark):
                        px, py = int(lm.x * w), int(lm.y * h)
                        cv2.putText(img, str(id), (px, py - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 0, 0), 1)

                allHands.append(myHand)

        return allHands, img

    def fingersUp(self, myHand):
        fingers = []
        lmList = myHand["lmList"]
        handType = myHand["type"]

        # Thumb: Distance-based detection with fallback angle
        thumb_tip = lmList[4]  # Tip (4)
        thumb_mcp = lmList[2]  # MCP (2)
        dx = thumb_tip[0] - thumb_mcp[0]  # X difference
        dy = thumb_tip[1] - thumb_mcp[1]  # Y difference
        distance = math.sqrt(dx**2 + dy**2)

        # Angle calculation as fallback
        thumb_ip = lmList[3]  # IP (3)
        x1, y1 = thumb_mcp
        x2, y2 = thumb_ip
        x3, y3 = thumb_tip
        angle = math.degrees(math.atan2(y3 - y2, x3 - x2) - math.atan2(y1 - y2, x1 - x2))
        if angle < 0:
            angle += 360

        # Thumb up if distance is significant or angle indicates extension
        if handType == "Right":
            if dx < -30 or (45 < angle < 135 and distance > 30):  # Left extension or angle
                fingers.append(1)
            else:
                fingers.append(0)
        else:  # Left hand
            if dx > 30 or (45 < angle < 135 and distance > 30):  # Right extension or angle
                fingers.append(1)
            else:
                fingers.append(0)

        # Other fingers: Check if tip is above DIP joint
        dipIds = [5, 9, 13, 17]  # DIP joints for Index, Middle, Ring, Pinky
        for id in range(1, 5):  # Index, Middle, Ring, Pinky
            tip_y = lmList[self.tipIds[id]][1]
            dip_y = lmList[dipIds[id - 1]][1]
            if tip_y < dip_y - 20:  # Tip above DIP with threshold
                fingers.append(1)
            else:
                fingers.append(0)

        return fingers
    