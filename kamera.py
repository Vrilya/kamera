import cv2
import subprocess
import requests
import os
import time
from datetime import datetime

# Kontrollera om mappen "video" finns, annars skapa den
if not os.path.exists('video'):
    os.makedirs('video')

# RTSP URL för din kamera
rtsp_url = 'rtsp://admin:pinkod här@192.168.1.39:554/live/profile.0/video'

# Anslut till RTSP-strömmen
cap = cv2.VideoCapture(rtsp_url)

# Skapa en bakgrundssubtraktor
fgbg = cv2.createBackgroundSubtractorMOG2()

# Definiera ett specifikt område (ROI) i bilden
roi = (950, 100, 690, 550)

# Variabler för push-notifikation och initialisering
start_time = time.time()
notify_interval = 300  # 5 minuter
initialization_time = 30  # 30 sekunder för initialisering
last_notify_time = 0

def send_push_notification(token, message):
    """Skickar en pushnotis via Pushbullet."""
    url = 'https://api.pushbullet.com/v2/pushes'
    headers = {
        'Access-Token': token,
        'Content-Type': 'application/json'
    }
    data = {
        'type': 'note',
        'title': 'Rörelsedetektering',
        'body': message
    }
    response = requests.post(url, json=data, headers=headers)
    return response.status_code == 200

# Variabler för videoinspelning
is_recording = False
last_motion_time = 0
video_duration = 60  # 60 sekunder
recording_process = None
recording_start_time = None

# Buffert och känslighet för rörelsedetektion
average_buffer = []
buffer_size = 100  # Justera storleken efter behov
sensitivity = 40000  # Justera detta värde för att öka eller minska känsligheten
locked_average = None  # Låst medelvärde när inspelning startar
recording_timer = 0  # Timer för inspelningens längd

# Funktion för att avsluta ffmpeg-inspelningen
def stop_recording(process):
    if process and process.poll() is None:
        try:
            process.stdin.write(b'q')
            process.stdin.flush()
        except Exception as e:
            print("Ett fel uppstod vid avslutning av inspelning:", e)
        finally:
            process.wait()

while True:
    try:
        ret, frame = cap.read()
        if not ret:
            break

        roi_frame = frame[roi[1]:roi[1]+roi[3], roi[0]:roi[0]+roi[2]]
        fgmask = fgbg.apply(roi_frame)
        count = cv2.countNonZero(fgmask)
        current_time = time.time()

        # Uppdatera glidande medelvärde om inte inspelning pågår
        if not is_recording:
            if len(average_buffer) < buffer_size:
                average_buffer.append(count)
            else:
                average_buffer.pop(0)
                average_buffer.append(count)
            average_count = sum(average_buffer) / len(average_buffer)
        else:
            # Uppdatera timer om inspelning pågår
            recording_timer -= current_time - last_motion_time
            last_motion_time = current_time

        # Kontrollera om initialiseringstiden är över
        if current_time - start_time > initialization_time:
            # Kontrollera för signifikant rörelse
            if not is_recording and count > average_count + sensitivity:
                # Lås medelvärdet och starta inspelning
                locked_average = average_count
                recording_timer = video_duration
                last_motion_time = current_time
                is_recording = True
                recording_start_time = current_time
                timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                video_filename = f"video/rörelsedetektering_{timestamp}.mp4"

                command = [
                    'ffmpeg',
                    '-i', rtsp_url,
                    '-c:v', 'copy',
                    '-c:a', 'copy',
                    video_filename
                ]
                recording_process = subprocess.Popen(command, stdin=subprocess.PIPE)

            # Återställ timer om signifikant rörelse upptäcks under inspelning
            elif is_recording and count > locked_average + sensitivity:
                recording_timer = video_duration

            # Skicka push-notifikation
#            if current_time - last_notify_time > notify_interval and is_recording:
#                message = f"Rörelse upptäckt vid dörren! {count} pixlar upptäckta."
#                print(message)
#                if send_push_notification('token här', message):
#                    print("Pushnotis skickad.")
#                    last_notify_time = current_time

            # Stoppa inspelning när timer går ut
            if is_recording and recording_timer <= 0:
                stop_recording(recording_process)
                recording_process = None
                is_recording = False
                locked_average = None

        # Visa bildrutor (valfritt)
#        cv2.imshow('Frame', frame)
#        cv2.imshow('ROI', roi_frame)
#        cv2.imshow('Mask', fgmask)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    except Exception as e:
        print("Ett fel uppstod:", e)
        cap.release()
        if recording_process:
            stop_recording(recording_process)
            recording_process = None
        cap = cv2.VideoCapture(rtsp_url)
        time.sleep(5)

# Städning vid avslutning
if recording_process:
    stop_recording(recording_process)

cap.release()
cv2.destroyAllWindows()
