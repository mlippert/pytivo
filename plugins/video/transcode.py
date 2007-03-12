import subprocess, shutil, os, re, sys, ConfigParser, time, lrucache 

from Config import config

info_cache = lrucache.LRUCache(1000)

FFMPEG = config.get('Server', 'ffmpeg')
#SCRIPTDIR = os.path.dirname(__file__)
#FFMPEG = os.path.join(SCRIPTDIR, 'ffmpeg_mp2.exe')
#FFMPEG = '/usr/bin/ffmpeg'

# XXX BIG HACK
# subprocess is broken for me on windows so super hack
def patchSubprocess():
    o = subprocess.Popen._make_inheritable

    def _make_inheritable(self, handle):
        if not handle: return subprocess.GetCurrentProcess()
        return o(self, handle)

    subprocess.Popen._make_inheritable = _make_inheritable
mswindows = (sys.platform == "win32")
if mswindows:
    patchSubprocess()
        
def output_video(inFile, outFile):
    if tivo_compatable(inFile):
        f = file(inFile, 'rb')
        shutil.copyfileobj(f, outFile)
        f.close() 
    else:
        transcode(inFile, outFile)

def transcode(inFile, outFile):
    cmd = [FFMPEG, '-i', inFile, '-vcodec', 'mpeg2video', '-r', '29.97', '-b', '4096K'] + select_aspect(inFile)  +  ['-comment', 'pyTivo.py', '-ac', '2', '-ab', '192','-ar', '44100', '-f', 'vob', '-' ]   
    ffmpeg = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    try:
        shutil.copyfileobj(ffmpeg.stdout, outFile)
    except:
        kill(ffmpeg.pid)
       
def select_aspect(inFile):
    type, width, height, fps, millisecs =  video_info(inFile)
    
    d = gcd(height,width)
    ratio = (width*100)/height
    rheight, rwidth = height/d, width/d

    if (rheight, rwidth) in [(4, 3), (10, 11), (15, 11), (59, 54), (59, 72), (59, 36), (59, 54)]:
        return ['-aspect', '4:3', '-s', '720x480']
    elif (rheight, rwidth) in [(16, 9), (20, 11), (40, 33), (118, 81), (59, 27)]:
        return ['-aspect', '16:9', '-s', '720x480']
    #If video is nearly 4:3 or 16:9 go ahead and strech it
    elif ((ratio <= 141) and (ratio >= 125)):
        return ['-aspect', '4:3', '-s', '720x480']
    elif ((ratio <= 185) and (ratio >= 169)):
        return ['-aspect', '16:9', '-s', '720x480']
    else:
        settings = []
        settings.append('-aspect')
        settings.append('4:3')
        #If video is wider than 4:3 add top and bottom padding
        if (ratio > 133):
      
            endHeight = (720*height)/width
            if endHeight % 2:
                endHeight -= 1

            settings.append('-s')
            settings.append('720x' + str(endHeight))

            topPadding = ((480 - endHeight)/2)
            if topPadding % 2:
                topPadding -= 1
            
            settings.append('-padtop')
            settings.append(str(topPadding))
            bottomPadding = (480 - endHeight) - topPadding
            settings.append('-padbottom')
            settings.append(str(bottomPadding))
            
            return settings
        #If video is taller than 4:3 add left and right padding, this is rare
        else:
            endWidth = (480*width)/height
            if endWidth % 2:
                endWidth -= 1

            settings.append('-s')
            settings.append(str(endWidth) + 'x480')

            leftPadding = ((720 - endWidth)/2)
            if leftPadding % 2:
                leftPadding -= 1
        
            settings.append('-padleft')
            settings.append(str(leftPadding))
            rightPadding = (720 - endWidth) - leftPadding
            settings.append('-padright')
            settings.append(str(rightPadding))            
            return settings

def tivo_compatable(inFile):
    suportedModes = [[720, 480], [704, 480], [544, 480], [480, 480], [352, 480]]
    type, width, height, fps, millisecs =  video_info(inFile)
    #print type, width, height, fps, millisecs

    if (inFile[-5:]).lower() == '.tivo':
        return True

    if not type == 'mpeg2video':
        #print 'Not Tivo Codec'
        return False

    if not fps == '29.97':
        #print 'Not Tivo fps'
        return False

    for mode in suportedModes:
        if (mode[0], mode[1]) == (width, height):
            #print 'Is TiVo!'
            return True
        #print 'Not Tivo dimensions'
    return False

def video_info(inFile):
    if inFile in info_cache:
        return info_cache[inFile]

    if (inFile[-5:]).lower() == '.tivo':
        info_cache[inFile] = (True, True, True, True, True)
        return True, True, True, True, True

    cmd = [FFMPEG, '-i', inFile ] 
    ffmpeg = subprocess.Popen(cmd, stderr=subprocess.PIPE, stdout=subprocess.PIPE, stdin=subprocess.PIPE)

    # wait 4 sec if ffmpeg is not back give up
    for i in range(80):
        time.sleep(.05)
        if not ffmpeg.poll() == None:
            break
    
    if ffmpeg.poll() == None:
        kill(ffmpeg.pid)
        info_cache[inFile] = (None, None, None, None, None)
        return None, None, None, None, None

    output = ffmpeg.stderr.read()

    durre = re.compile(r'.*Duration: (.{2}):(.{2}):(.{2})\.(.),')
    d = durre.search(output)

    rezre = re.compile(r'.*Video: ([^,]+),.*')
    x = rezre.search(output)
    if x:
        codec = x.group(1)
    else:
        info_cache[inFile] = (None, None, None, None, None)
        return None, None, None, None, None

    rezre = re.compile(r'.*Video: .+, (\d+)x(\d+),.*')
    x = rezre.search(output)
    if x:
        width = int(x.group(1))
        height = int(x.group(2))
    else:
        info_cache[inFile] = (None, None, None, None, None)
        return None, None, None, None, None

    rezre = re.compile(r'.*Video: .+, (.+) fps.*')
    x = rezre.search(output)
    if x:
        fps = x.group(1)
    else:
        info_cache[inFile] = (None, None, None, None, None)
        return None, None, None, None, None

    rezre = re.compile(r'.*film source: (\d+).*')
    x = rezre.search(output.lower())
    if x:
        fps = x.group(1)

    millisecs = ((int(d.group(1))*3600) + (int(d.group(2))*60) + int(d.group(3)))*1000 + (int(d.group(4))*100)
    info_cache[inFile] = (codec, width, height, fps, millisecs)
    return codec, width, height, fps, millisecs
       
def suported_format(inFile):
    if video_info(inFile)[0]:
        return video_info(inFile)[4]
    else:
        return False

def kill(pid):
    if mswindows:
        win32kill(pid)
    else:
        import os, signal
        os.kill(pid, signal.SIGKILL)

def win32kill(pid):
        import ctypes
        handle = ctypes.windll.kernel32.OpenProcess(1, False, pid)
        ctypes.windll.kernel32.TerminateProcess(handle, -1)
        ctypes.windll.kernel32.CloseHandle(handle)

def gcd(a,b):
    while b:
        a, b = b, a % b
    return a