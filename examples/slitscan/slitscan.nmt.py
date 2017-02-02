x = 0
idx = 0

def video_out(a):
    global idx
    
    a[:] = arr[idx]
    a[:,:idx] = arr[:idx,:,x].transpose((1,0,2))
    
    if idx<320:
        idx += 1
        
def mouse_in(type, px, py, button):
    global x
    x = px
