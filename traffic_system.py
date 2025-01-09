import threading
import subprocess
import os
import time
import webbrowser
import pygetwindow as gw
import pyautogui
from flask import Flask, Response
import cv2
from ultralytics import YOLO
import numpy as np

app = Flask(__name__)

# YOLOv8 모델 로드 (사전 훈련된 모델 사용)
model = YOLO('last.pt')  # YOLOv8 large 모델

# 특정 점들이 있는 폴리곤 안에 있는지 확인하는 함수
def is_in_polygon(center, polygon):
    return cv2.pointPolygonTest(polygon, center, False) >= 0

# 차량 수에 따라 교통 상태를 결정하는 함수
def get_traffic_status(count):
    if count <= 7:
        return "Free-flowing traffic", (0, 255, 0)  # 초록색
    elif 8 <= count <= 14:
        return "Slow-moving traffic", (0, 255, 255)  # 노란색
    elif count >= 15:
        return "Heavy traffic", (0, 0, 255)  # 빨간색

def video_stream():
    # 비디오 파일 경로 설정
    video_path = "cctv4.mp4"
    cap = cv2.VideoCapture(video_path)
    
    while cap.isOpened():
        ret, frame = cap.read()  # 비디오에서 프레임 읽기
        if not ret:
            break

        frame_height, frame_width = frame.shape[:2]

        # 좌측 하행과 우측 상행의 ROI 다각형 설정 (4개의 점)
        left_polygon = np.array([[frame_height * 0.2, frame_height], [frame_width * 0.5, frame_height * 0.6],  
        [frame_width * 0.6, frame_height * 0.6], [frame_width * 0.35, frame_height]], np.int32)

        right_polygon = np.array([[frame_width * 0.4, frame_height], [frame_width * 0.65, frame_height * 0.6],
        [frame_width* 0.75, frame_height * 0.6], [frame_width* 0.6, frame_height]], np.int32)

        # 다각형을 그리기 (시각화)
        cv2.polylines(frame, [left_polygon], isClosed=True, color=(255, 0, 0), thickness=2)  # 파란색
        cv2.polylines(frame, [right_polygon], isClosed=True, color=(0, 0, 255), thickness=2)  # 빨간색

        # 현재 프레임에서 좌측 하행, 우측 상행의 차량 카운트
        left_roi_count = 0
        right_roi_count = 0

        # YOLOv8 모델로 객체 탐지 적용
        results = model(frame)
        
        
        for result in results:
            for box in result.boxes:
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                    # 바운딩 박스의 중심 좌표 계산
                center_x = (x1 + x2) / 2
                center_y = (y1 + y2) / 2
                center = (int(center_x), int(center_y))
                    
                    # 좌측 하행과 우측 상행의 다각형 안에 있는지 확인
                if is_in_polygon(center, left_polygon):
                    left_roi_count += 1
                        # 좌측 하행 영역에 있는 차량 바운딩 박스 그리기 (파란색)
                    cv2.rectangle(frame, (int(x1), int(y1)), (int(x2), int(y2)), (255, 0, 0), 2)  # 파란색 바운딩 박스
                elif is_in_polygon(center, right_polygon):
                    right_roi_count += 1
                    # 우측 상행 영역에 있는 차량 바운딩 박스 그리기 (빨간색)
                    cv2.rectangle(frame, (int(x1), int(y1)), (int(x2), int(y2)), (0, 0, 255), 2)  # 빨간색 바운딩 박스

        # 좌측 하행과 우측 상행의 차량 수 및 교통 상태를 계산하여 화면에 표시
        left_status, left_color = get_traffic_status(left_roi_count)
        right_status, right_color = get_traffic_status(right_roi_count)
        
        # 좌측 하행 차량 수 및 상태 표시
        cv2.putText(frame, f'down: {left_roi_count} ({left_status})', (20, 450), cv2.FONT_HERSHEY_SIMPLEX, 3, left_color, 9)
        # 우측 상행 차량 수 및 상태 표시
        cv2.putText(frame, f'up: {right_roi_count} ({right_status})', (20, 550), cv2.FONT_HERSHEY_SIMPLEX, 3, right_color, 9)
        
        # 시각화된 프레임을 JPEG로 인코딩
        _, jpeg = cv2.imencode('.jpg', frame)
        frame = jpeg.tobytes()
        
        # 프레임을 반환하여 스트리밍
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n\r\n')
    
    cap.release()  # 비디오 파일이 끝나면 자원 해제

@app.route('/video_feed')
def video_feed():
    # 클라이언트가 '/video_feed'로 접속하면 비디오 스트리밍 시작
    return Response(video_stream(), mimetype='multipart/x-mixed-replace; boundary=frame')

# Flask 서버 실행 함수
def run_flask():
    app.run(host='0.0.0.0', port=5000, debug=False)

# Flask 서버를 별도의 스레드로 실행
flask_thread = threading.Thread(target=run_flask)
flask_thread.daemon = True
flask_thread.start()

# Mission Planner 실행 함수
def launch_mission_planner():
    mission_planner_path = r"C:\MissionPlanner\bin\Debug\net461\MissionPlanner.exe"  # 실제 경로
    mission_planner_dir = os.path.dirname(mission_planner_path)
    
    try:
        subprocess.run([mission_planner_path], cwd=mission_planner_dir, check=True)
    except FileNotFoundError:
        print(f"Error: {mission_planner_path} 파일을 찾을 수 없습니다.")
    except Exception as e:
        print(f"Mission Planner 실행 중 오류 발생: {e}")

# Mission Planner 실행 (별도의 스레드에서 실행)
mission_planner_thread = threading.Thread(target=launch_mission_planner)
mission_planner_thread.start()

# 서버가 실행될 때까지 대기
time.sleep(3)

# 웹 브라우저로 비디오 스트림 열기
webbrowser.open_new("http://localhost:5000/video_feed")

# Flask와 Mission Planner의 창을 나란히 배치하기 위한 코드
def position_windows():
    time.sleep(5)  # 창이 완전히 로드되기까지 대기

    # Mission Planner 창을 찾고 화면 왼쪽에 배치
    mp_window = gw.getWindowsWithTitle("Mission Planner")[0]
    if mp_window:
        mp_window.moveTo(0, 0)  # 좌상단에 창 이동
        mp_window.resizeTo(960, 1080)  # 창 크기 설정

    # 웹 브라우저 창을 찾아 오른쪽에 배치
    browser_window = gw.getWindowsWithTitle("localhost")[0]
    if browser_window:
        browser_window.moveTo(960, 0)  # 화면 오른쪽으로 창 이동
        browser_window.resizeTo(960, 1080)  # 창 크기 설정

position_windows()

# 모든 스레드가 종료될 때까지 대기
mission_planner_thread.join()
flask_thread.join()
