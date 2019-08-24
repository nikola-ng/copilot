from camera import CAMERA
from yolo_model import BoundBox,  YOLO 
from utils.bbox import bbox_iou 
from lane_detection import LANE_DETECTION, OBSTACLE,obstructions,create_queue, plt
import numpy as np
import cv2
from datetime import datetime



class FRAME :
    fps:float
    camera : CAMERA
    yolo : classmethod
    PERSP_PERIOD =  100000
    YOLO_PERIOD = 2 # SECONDS
    verbose = 3

    yellow_lower = np.uint8([ 20, 50,   50]),
    yellow_upper = np.uint8([35, 255, 255]),
    white_lower = np.uint8([ 0, 200,   0]),
    white_upper = np.uint8([180, 255, 100]), 
    lum_factor = 150,
    max_gap_th = 2/5,
    lane_start=[0.35,0.75] , 


    time =  datetime.utcnow().timestamp()
    l_gap_skipped = 0
    l_breached = 0 
    l_reset = 0 
    l_appended = 0

    
    n_gap_skipped = 0
    n_breached = 0 
    n_reset = 0 
    n_appended = 0
    _defaults = {
        "id": 0,
        "first": True,
        "speed": 0,
        "n_objects" :0,
         "camera" : CAMERA(),
        "image" : [],
        "LANE_WIDTH" :  3.66,
        "fps" :22,
        'verbose' :  3,
        "yellow_lower" : np.uint8([ 20, 50,   50]),
        "yellow_upper" : np.uint8([35, 255, 255]),
        "white_lower" : np.uint8([ 0, 200,   0]),
        "white_upper" : np.uint8([180, 255, 100]), 
        "lum_factor" : 150,
        "max_gap_th" : 2/5,
        "lane_start":[0.35,0.75] , 
        "verbose" : 3
        }
    
    @classmethod
    def get_defaults(cls, n):
        if n in cls._defaults:
            return cls._defaults[n]
        else:
            return "Unrecognized attribute name '" + n + "'"  

    def __init__(self, **kwargs):
        # calc pers => detect cars and dist > detect lanes
      
        self.__dict__.update(self._defaults) # set up default values
        self.__dict__.update(kwargs) # and update with user overrides
        self.speed =  self.get_speed()
        ### IMAGE PROPERTIES
        self.image : np.ndarray
        if  self.image.size ==0 :
            raise ValueError("No Image") 
      
        
        self.temp_dir = './images/detection/'
        self.perspective_done_at = datetime.utcnow().timestamp()
        self.img_shp =  (self.image.shape[1], self.image.shape[0] )
        self.area =  self.img_shp[0]*self.img_shp[1]
        # self.image =  self.camera.undistort(self.image)
        ### OBJECT DETECTION AND TRACKING
        self.yolo =  YOLO()
        self.first_detect = True
        self.obstacles :[OBSTACLE] =[]
        self.__yp = int(self.YOLO_PERIOD*self.fps)
        ### LANE FINDER 
        self.count = 0
        self.lane = LANE_DETECTION(self.image, self.fps,\
            verbose=self.verbose, 
            yellow_lower =self.yellow_lower,
            yellow_upper = self.yellow_upper,
            white_lower = self.white_lower,
            white_upper = self.white_upper, 
            lum_factor = self.lum_factor,
            max_gap_th = self.max_gap_th,
            lane_start=self.lane_start ,
        )


    def perspective_tfm(self ,  pos) : 
        now  = datetime.utcnow().timestamp()
        if now - self.perspective_done_at > self.PERSP_PERIOD :
            self.lane = LANE_DETECTION(self.image,self.fps,verbose=self.verbose)
        return cv2.perspectiveTransform(pos, self.lane.trans_mat)

    def determine_stats(self):
        n = 5
        t  = datetime.utcnow().timestamp()
        dt = int(t - self.time)
        if self.count % (self.fps * n) == 0:
            
            self.n_gap_skipped = int((self.lane.n_gap_skip - self.l_gap_skipped) *100 / (self.fps * n))
            self.n_appended = int((self.lane.lane.appended - self.l_appended) *100 / (self.fps * n))
            self.n_breached = int((self.lane.lane.breached - self.l_breached) *100 / (self.fps * n))
            self.n_reset = int((self.lane.lane.reset - self.l_reset) *100 / (self.fps * n))

           
            self.l_gap_skipped = self.lane.n_gap_skip 
            self.l_appended = self.lane.lane.appended 
            self.l_breached = self.lane.lane.breached
            self.l_reset = self.lane.lane.reset 
            print("SKIPPED {:d}% BREACHED {:d}% RESET {:d}% APPENDED {:d}% | Time {:d}s , Processing FPS {:.2f} vs Desired FPS {:.2f}  "\
                .format(self.n_gap_skipped, self.n_breached, self.n_reset, self.n_appended,\
                    dt, self.fps * n / dt, self.fps ))
            self.time=t
    def get_speed(self):
        return 30
    


    
    def process_and_plot(self,image):
        self.update_trackers(image)
        lane_img = self.lane.process_image( image, self.obstacles)
        self.determine_stats()
        return lane_img

    @staticmethod
    def corwh2box(corwh):
        box=BoundBox( int(corwh[0]), int(corwh[1]), int(corwh[0] + corwh[2]), int(corwh[1] + corwh[3]))
        return box

    def tracker2object(self, boxes : [OBSTACLE], th =  0.5) : 
        n_b = len(boxes)
        n_o =  len(self.obstacles)
        iou_mat =  np.zeros((n_o,n_b))
        for i in range(n_o):
            for j in range(n_b):
                iou_mat[i,j] =  bbox_iou(self.obstacles[i],boxes[j])
        count =  min(n_b,n_o)
        used = []
        idmax = 0
        obstacles =[]
        while count >0 :
            r,k  = np.unravel_index(np.argmax(iou_mat, axis=None), iou_mat.shape)
            if iou_mat[r,k] > th :
                used.append(k)
                obstacle  = self.obstacles[r]
                box = boxes[k]
                if idmax < obstacle._id :
                    idmax = obstacle._id 
                obstacle.update_box(box)
                obstacles.append(obstacle)
            iou_mat[r,:] =  -99
            iou_mat[:,k] =  -99
            count = count -1
        idx = range(n_b)
        idx =  [elem for elem in idx if elem not in used]
        self.obstacles = obstacles
        for i, c in enumerate(idx):
            # dst  =  self.calculate_position(boxes[c])
            obstacle = OBSTACLE(boxes[c],i+idmax+1)
            self.obstacles.append(obstacle)
        return
    
    def update_trackers(self, img):
        image = img.copy()
        for n, obs in enumerate(self.obstacles):

            success, corwh = obs.tracker.update(image)
            if not success :
                del self.obstacles[n]

                continue
            box = self.corwh2box(corwh)
            # dst = self.calculate_position( box)  
            self.obstacles[n].update_coord(box)
        
        if self.count% self.__yp == 0 :
            boxes= self.yolo.make_predictions(image,obstructions = obstructions,plot=True) 
            self.tracker2object(boxes)
            image  =  cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
            n_obs =  len(self.obstacles)
            for i in range(n_obs):
                tracker = cv2.TrackerKCF_create()# cv2.TrackerMIL_create()#  # Note: Try comparing KCF with MIL
                box = self.obstacles[i]
                bbox = (box.xmin, box.ymin, box.xmax-box.xmin, box.ymax-box.ymin)
                # print(bbox)
                success = tracker.init(image, bbox )
                if success :
                    self.obstacles[i].tracker=tracker

        
        self.count +=1

           
        return



    def warp(self, img):
        now  = datetime.utcnow().timestamp()
        if now - self.perspective_done_at > self.PERSP_PERIOD :
            self.lane = LANE_DETECTION(self.image,self.fps)
        return cv2.warpPerspective(img, self.lane.trans_mat, self.lane.UNWARPED_SIZE, flags=cv2.WARP_FILL_OUTLIERS+cv2.INTER_CUBIC)

    def unwarp(self, img):
        now  = datetime.utcnow().timestamp()
        if now - self.perspective_done_at > self.PERSP_PERIOD :
            self.lane = LANE_DETECTION(self.image,self.fps)
        return cv2.warpPerspective(img, self.lane.trans_mat, self.img_shp, flags=cv2.WARP_FILL_OUTLIERS +
                                                                     cv2.INTER_CUBIC+cv2.WARP_INVERSE_MAP)
    def process_video(self, ):
        video_reader =  cv2.VideoCapture("videos/challenge_video_edit.mp4") 
        fps =  video_reader.get(cv2.CAP_PROP_FPS)
        fps_factor = 2
        fps_adjusted =  fps//fps_factor
        nb_frames = int(video_reader.get(cv2.CAP_PROP_FRAME_COUNT))
        frame_h = int(video_reader.get(cv2.CAP_PROP_FRAME_HEIGHT))
        frame_w = int(video_reader.get(cv2.CAP_PROP_FRAME_WIDTH))
        video_out = "videos/output11.mov"
        video_writer = cv2.VideoWriter(video_out,cv2.VideoWriter_fourcc('m', 'p', '4', 'v'), fps, (frame_w, frame_h))
        pers_frame_time =14#180# 310# seconds
        pers_frame = int(pers_frame_time *fps)
        video_reader.set(1,pers_frame)
        ret, image = video_reader.read()
        frame = FRAME(image=image, fps =  fps_adjusted, verbose =2)
        frames = nb_frames
        t0  =.180#310 # sec
        t1 = int(frames/fps) #sec
        dur = t1 -t0
        video_reader.set(1,t0*fps)
        # start = datetime.utcnow().timestamp()
        for i in tqdm(range(int(t0*fps), int(t1*fps)),mininterval=3):
            if i % fps_factor == 0 :  
                status, image = video_reader.read()
                if  status :
                    try : 
                        procs_img = frame.process_and_plot(image)
                        video_writer.write(procs_img) 
                    except :
                        print("\n\rGOT EXEPTION TO PROCES THE IMAGE\033[F", frame.count)
                        l1 =  frame.lane.white_lower[1]
                        frame.lane.compute_bounds(image)
                        print(l1,"->",frame.lane.white_lower[1])
        # stop =datetime.utcnow().timestamp()
        print("SKIPPED {:d} BREACHED {:d} RESET {:d} APPENDED {:d} | Total {:d} ".\
            format(frame.lane.n_gap_skip, frame.lane.lane.breached,\
                frame.lane.lane.reset,frame.lane.lane.appended, frame.count))
        video_reader.release()
        video_writer.release() 
        cv2.destroyAllWindows()


    
     
    
    
    def vehicle_speed(self) :
        return
        
if __name__ == "__main__":
    from tqdm import tqdm
    
    # video_reader =  cv2.VideoCapture("videos/challenge_video.mp4") 
    video_reader =  cv2.VideoCapture("videos/challenge_video_edit.mp4") 
    # video_reader =  cv2.VideoCapture("videos/harder_challenge_video.mp4") 
    # video_reader =  cv2.VideoCapture("videos/nice_road.mp4")
    # video_reader =  cv2.VideoCapture("videos/nh60.mp4")
    fps =  video_reader.get(cv2.CAP_PROP_FPS)
    fps_factor = 2
    fps_adjusted =  fps//fps_factor
    nb_frames = int(video_reader.get(cv2.CAP_PROP_FRAME_COUNT))
    frame_h = int(video_reader.get(cv2.CAP_PROP_FRAME_HEIGHT))
    frame_w = int(video_reader.get(cv2.CAP_PROP_FRAME_WIDTH))
    video_out = "videos/output11.mov"
    video_writer = cv2.VideoWriter(video_out,cv2.VideoWriter_fourcc('m', 'p', '4', 'v'), fps, (frame_w, frame_h))
    pers_frame_time =14#180# 310# seconds
    pers_frame = int(pers_frame_time *fps)
    video_reader.set(1,pers_frame)
    ret, image = video_reader.read()
    frame = FRAME(image=image, fps =  fps_adjusted, verbose =2)
    frames = nb_frames
    t0  =.180#310 # sec
    t1 = int(frames/fps) #sec
    dur = t1 -t0
    video_reader.set(1,t0*fps)
    # start = datetime.utcnow().timestamp()
    for i in tqdm(range(int(t0*fps), int(t1*fps)),mininterval=3):
        if i % fps_factor == 0 :  
            status, image = video_reader.read()
            if  status :
                try : 
                    procs_img = frame.process_and_plot(image)
                    video_writer.write(procs_img) 
                except :
                    print("\n\rGOT EXEPTION TO PROCES THE IMAGE\033[F", frame.count)
                    l1 =  frame.lane.white_lower[1]
                    frame.lane.compute_bounds(image)
                    print(l1,"->",frame.lane.white_lower[1])
    # stop =datetime.utcnow().timestamp()
    print("SKIPPED {:d} BREACHED {:d} RESET {:d} APPENDED {:d} | Total {:d} ".\
         format(frame.lane.n_gap_skip, frame.lane.lane.breached,\
             frame.lane.lane.reset,frame.lane.lane.appended, frame.count))
    video_reader.release()
    video_writer.release() 
    cv2.destroyAllWindows()


