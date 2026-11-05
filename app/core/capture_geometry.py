"""Qt-independent logical/physical capture plans and normalized raster assembly."""
from dataclasses import dataclass
import math


@dataclass(frozen=True)
class ScreenDescriptor:
    logical_rect: tuple[int,int,int,int]
    physical_origin: tuple[int,int]
    dpr: float
    name: str = ''
    physical_size: tuple[int,int] | None = None


@dataclass(frozen=True)
class CapturePiece:
    screen: ScreenDescriptor
    logical_rect: tuple[int,int,int,int]
    physical_rect: tuple[int,int,int,int]
    canvas_rect: tuple[int,int,int,int]


@dataclass(frozen=True)
class CapturePlan:
    logical_rect: tuple[int,int,int,int]
    canvas_size: tuple[int,int]
    canvas_dpr: float
    pieces: tuple[CapturePiece,...]

    @property
    def physical_bounds(self):
        left=min(piece.physical_rect[0] for piece in self.pieces)
        top=min(piece.physical_rect[1] for piece in self.pieces)
        right=max(piece.physical_rect[0]+piece.physical_rect[2] for piece in self.pieces)
        bottom=max(piece.physical_rect[1]+piece.physical_rect[3] for piece in self.pieces)
        return left,top,right-left,bottom-top

    @property
    def needs_composition(self):
        if len(self.pieces)!=1:return True
        piece=self.pieces[0]
        return piece.canvas_rect!=(0,0,*self.canvas_size) or piece.physical_rect[2:]!=self.canvas_size


def intersection(a,b):
    left=max(a[0],b[0]);top=max(a[1],b[1])
    right=min(a[0]+a[2],b[0]+b[2]);bottom=min(a[1]+a[3],b[1]+b[3])
    return (left,top,right-left,bottom-top) if right>left and bottom>top else None


def build_capture_plan(logical_rect,screens,canvas_dpr=None,max_pixels=16_000_000):
    region=tuple(logical_rect)
    if len(region)!=4 or any(not math.isfinite(value) for value in region) or min(region[2:])<=0:
        raise ValueError('geçersiz mantıksal yakalama alanı')
    visible=[]
    for screen in screens:
        if not math.isfinite(screen.dpr) or screen.dpr<=0 or min(screen.logical_rect[2:])<=0:
            raise ValueError('geçersiz ekran ölçeği veya alanı')
        area=intersection(region,screen.logical_rect)
        if area is not None:visible.append((screen,area))
    if not visible:raise ValueError('yakalama alanı hiçbir ekrana değmiyor')
    scale=max(screen.dpr for screen,_ in visible) if canvas_dpr is None else canvas_dpr
    if not math.isfinite(scale) or scale<=0:raise ValueError('geçersiz ortak yakalama ölçeği')
    size=(math.ceil(region[2]*scale),math.ceil(region[3]*scale))
    if size[0]*size[1]>max_pixels:raise ValueError('yakalama alanı çok büyük; daha küçük bir alan seçin')
    pieces=[]
    scale_x=size[0]/region[2];scale_y=size[1]/region[3]
    for screen,area in visible:
        x,y,w,h=area;sx,sy,_,_=screen.logical_rect;px,py=screen.physical_origin
        left=px+math.floor((x-sx)*screen.dpr);top=py+math.floor((y-sy)*screen.dpr)
        right=px+math.ceil((x+w-sx)*screen.dpr);bottom=py+math.ceil((y+h-sy)*screen.dpr)
        physical_size=getattr(screen,'physical_size',None)
        if physical_size is not None:
            left=max(px,left);top=max(py,top)
            right=min(px+physical_size[0],right);bottom=min(py+physical_size[1],bottom)
        cx=round((x-region[0])*scale_x);cy=round((y-region[1])*scale_y)
        cr=round((x+w-region[0])*scale_x);cb=round((y+h-region[1])*scale_y)
        if min(right-left,bottom-top,cr-cx,cb-cy)<=0:continue
        pieces.append(CapturePiece(screen,area,(left,top,right-left,bottom-top),(cx,cy,cr-cx,cb-cy)))
    if not pieces:raise ValueError('yakalanabilir ekran parçası bulunamadı')
    return CapturePlan(region,size,scale,tuple(pieces))


def capture_canvas(plan,grab):
    """Grab each physical piece separately; return one uniformly scaled canvas.

    White gaps represent logical desktop space with no screen. No physical
    bounding-union image is assumed affine on a mixed-DPI desktop. A failed
    piece invalidates the entire frame instead of supplying incomplete OCR.
    """
    import cv2
    import numpy as np
    canvas=None
    for piece in plan.pieces:
        image=grab(*piece.physical_rect)
        if image is None:return None
        if image.ndim!=3 or image.shape[2]!=3 or image.dtype!=np.uint8:
            raise ValueError('ekran parçasının görüntü biçimi geçersiz')
        if image.shape[:2]!=(piece.physical_rect[3],piece.physical_rect[2]):
            raise ValueError('ekran parçasının piksel boyutu eşleşmiyor')
        if not plan.needs_composition:return image
        if canvas is None:canvas=np.full((plan.canvas_size[1],plan.canvas_size[0],3),255,np.uint8)
        x,y,w,h=piece.canvas_rect
        if image.shape[:2]!=(h,w):
            image=cv2.resize(image,(w,h),interpolation=cv2.INTER_LINEAR)
        canvas[y:y+h,x:x+w]=image
    return canvas
