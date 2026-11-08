package cn.startrail.helper;

import android.accessibilityservice.*;
import android.content.*;
import android.graphics.*;
import android.hardware.HardwareBuffer;
import android.os.*;
import android.view.*;
import android.view.accessibility.*;
import android.widget.*;
import java.util.function.Consumer;

public final class GameAccessibilityService extends AccessibilityService {
    static final String GAME="com.tencent.nrc";
    static GameAccessibilityService instance;
    final Handler handler=new Handler(Looper.getMainLooper());
    Engine engine;
    String foreground="";
    boolean gestureBusy=false;
    WindowManager windows;
    LinearLayout overlay;
    TextView overlayStatus;
    Button pauseButton;
    WindowManager.LayoutParams overlayParams;
    int screenWidth=3040,screenHeight=1904;
    int captureErrors=0;

    @Override protected void onServiceConnected(){
        instance=this;Store.init(this);engine=new Engine(this);windows=(WindowManager)getSystemService(WINDOW_SERVICE);
        Store.state("无障碍已连接，可在助手中读取实时列表");
    }
    @Override public void onAccessibilityEvent(AccessibilityEvent event){
        if(event.getEventType()==AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED&&event.getPackageName()!=null){
            String pkg=event.getPackageName().toString();
            if(!pkg.equals("com.android.systemui"))foreground=pkg;
        }
    }
    @Override public void onInterrupt(){if(engine!=null)engine.pause("无障碍服务被中断");}
    @Override public void onDestroy(){
        if(instance==this){if(engine!=null)engine.stop("服务已关闭");instance=null;}
        else if(engine!=null)engine.stopQuiet();
        hideOverlay();super.onDestroy();
    }
    boolean gameActive(){
        AccessibilityNodeInfo root=getRootInActiveWindow();
        if(root!=null&&root.getPackageName()!=null){String p=root.getPackageName().toString();root.recycle();return GAME.equals(p);}
        return GAME.equals(foreground);
    }
    void openGame(){
        Intent launch=getPackageManager().getLaunchIntentForPackage(GAME);
        if(launch==null){Store.state("未找到洛克王国：世界安卓客户端");return;}
        launch.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK|Intent.FLAG_ACTIVITY_RESET_TASK_IF_NEEDED);startActivity(launch);
    }
    void openHome(){
        Intent home=new Intent(this,MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK|Intent.FLAG_ACTIVITY_SINGLE_TOP);
        startActivity(home);
    }
    void capture(Consumer<Bitmap> done,Consumer<String> failed){
        if(!gameActive()){failed.accept("游戏未在前台");return;}
        TakeScreenshotCallback callback=new TakeScreenshotCallback(){
            @Override public void onSuccess(ScreenshotResult result){
                try(HardwareBuffer buffer=result.getHardwareBuffer()){
                    Bitmap hardware=Bitmap.wrapHardwareBuffer(buffer,result.getColorSpace());
                    if(hardware==null){failed.accept("截图缓冲区为空");return;}
                    Bitmap copy=hardware.copy(Bitmap.Config.ARGB_8888,false);hardware.recycle();
                    screenWidth=copy.getWidth();screenHeight=copy.getHeight();captureErrors=0;done.accept(copy);
                }catch(Exception e){failed.accept("截图转换失败："+e.getMessage());}
            }
            @Override public void onFailure(int code){captureErrors++;failed.accept("截图失败（"+code+"）");}
        };
        if(Build.VERSION.SDK_INT>=34){
            for(AccessibilityWindowInfo window:getWindows()){
                AccessibilityNodeInfo node=window.getRoot();
                if(node!=null){boolean game=GAME.contentEquals(node.getPackageName()==null?"":node.getPackageName());node.recycle();
                    if(game){takeScreenshotOfWindow(window.getId(),getMainExecutor(),callback);return;}}
            }
        }
        takeScreenshot(Display.DEFAULT_DISPLAY,getMainExecutor(),callback);
    }
    boolean tap(float x,float y,Runnable done){return gesture(x,y,x+.00001f,y,65,done);}
    boolean gesture(float x,float y,float endX,float endY,long duration,Runnable done){
        if(gestureBusy||!gameActive())return false;
        if(x<0||x>1||y<0||y>1||endX<0||endX>1||endY<0||endY>1)return false;
        Path path=new Path();path.moveTo(x*screenWidth,y*screenHeight);path.lineTo(endX*screenWidth,endY*screenHeight);
        GestureDescription description=new GestureDescription.Builder().addStroke(new GestureDescription.StrokeDescription(path,0,duration)).build();
        gestureBusy=true;setOverlayTouchable(false);
        final int generation=engine.generation;
        handler.postDelayed(()->{
            if(generation!=engine.generation||!Store.active||Store.paused||!gameActive()){gestureBusy=false;setOverlayTouchable(true);return;}
            boolean accepted=dispatchGesture(description,new GestureResultCallback(){
                @Override public void onCompleted(GestureDescription d){gestureBusy=false;setOverlayTouchable(true);if(done!=null)done.run();}
                @Override public void onCancelled(GestureDescription d){gestureBusy=false;setOverlayTouchable(true);Store.log("触摸被取消，已暂停以保留当前步骤");if(generation==engine.generation)engine.pause("触摸被系统中断，请确认游戏后继续");}
            },handler);
            if(!accepted){gestureBusy=false;setOverlayTouchable(true);if(generation==engine.generation)engine.pause("系统未接受触摸，请确认游戏后继续");}
        },60);
        return true;
    }
    int dp(float value){return Math.round(value*getResources().getDisplayMetrics().density);}
    void showOverlay(){
        if(overlay!=null)return;
        overlay=new LinearLayout(this);overlay.setOrientation(LinearLayout.VERTICAL);overlay.setPadding(dp(10),dp(7),dp(10),dp(7));
        android.graphics.drawable.GradientDrawable bg=new android.graphics.drawable.GradientDrawable();bg.setColor(0xef131b2f);bg.setCornerRadius(dp(14));bg.setStroke(dp(1),0xff665596);overlay.setBackground(bg);
        overlayStatus=new TextView(this);overlayStatus.setTextColor(0xffeaf0ff);overlayStatus.setTextSize(12);overlay.addView(overlayStatus);
        LinearLayout row=new LinearLayout(this);
        pauseButton=overlayButton("暂停",v->{if(Store.paused)engine.resume();else engine.pause("已手动暂停");});
        row.addView(pauseButton,new LinearLayout.LayoutParams(0,dp(36),1));
        row.addView(overlayButton("停止",v->engine.stop("已手动停止")),new LinearLayout.LayoutParams(0,dp(36),1));
        row.addView(overlayButton("主界面",v->{engine.pause("打开主界面");openHome();}),new LinearLayout.LayoutParams(0,dp(36),1));
        overlay.addView(row);
        overlayParams=new WindowManager.LayoutParams(dp(270),WindowManager.LayoutParams.WRAP_CONTENT,WindowManager.LayoutParams.TYPE_ACCESSIBILITY_OVERLAY,
                WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE|WindowManager.LayoutParams.FLAG_NOT_TOUCH_MODAL,PixelFormat.TRANSLUCENT);
        overlayParams.gravity=Gravity.TOP|Gravity.START;overlayParams.x=dp(15);overlayParams.y=dp(95);
        overlayStatus.setOnTouchListener(new View.OnTouchListener(){float downX,downY;int oldX,oldY;
            @Override public boolean onTouch(View v,android.view.MotionEvent e){
                if(e.getAction()==android.view.MotionEvent.ACTION_DOWN){downX=e.getRawX();downY=e.getRawY();oldX=overlayParams.x;oldY=overlayParams.y;return true;}
                if(e.getAction()==android.view.MotionEvent.ACTION_MOVE){overlayParams.x=oldX+(int)(e.getRawX()-downX);overlayParams.y=oldY+(int)(e.getRawY()-downY);windows.updateViewLayout(overlay,overlayParams);return true;}return true;}
        });
        windows.addView(overlay,overlayParams);updateOverlay();
    }
    Button overlayButton(String label,View.OnClickListener listener){Button b=new Button(this);b.setText(label);b.setTextSize(10);b.setTextColor(0xffdfe8ff);b.setBackgroundTintList(android.content.res.ColorStateList.valueOf(0xff29364e));b.setOnClickListener(listener);return b;}
    void updateOverlay(){if(overlayStatus!=null){overlayStatus.setText("✦ 星轨  "+Store.round+"/"+Store.total+"  成功 "+Store.succeeded+" · 失败 "+Store.failed+"\n"+Store.status);pauseButton.setText(Store.paused?"继续":"暂停");}}
    void hideOverlay(){if(overlay!=null){try{windows.removeView(overlay);}catch(Exception ignored){}overlay=null;overlayStatus=null;}}
    void setOverlayTouchable(boolean enabled){
        if(overlay==null||overlayParams==null)return;
        if(enabled)overlayParams.flags&=~WindowManager.LayoutParams.FLAG_NOT_TOUCHABLE;
        else overlayParams.flags|=WindowManager.LayoutParams.FLAG_NOT_TOUCHABLE;
        try{windows.updateViewLayout(overlay,overlayParams);}catch(Exception ignored){}
    }
    void calibrate(String key,String label){
        if(Store.active)engine.pause("校准触摸位置");hideOverlay();openGame();
        handler.postDelayed(()->{
            android.util.DisplayMetrics metrics=new android.util.DisplayMetrics();windows.getDefaultDisplay().getRealMetrics(metrics);
            TextView layer=new TextView(this);layer.setText("点击一次“"+label+"”的位置完成校准\n本次点击仅记录位置，不操作游戏");layer.setTextColor(0xffffffff);layer.setTextSize(20);layer.setGravity(Gravity.TOP|Gravity.CENTER_HORIZONTAL);layer.setPadding(0,dp(40),0,0);layer.setBackgroundColor(0x22000000);
            WindowManager.LayoutParams params=new WindowManager.LayoutParams(-1,-1,WindowManager.LayoutParams.TYPE_ACCESSIBILITY_OVERLAY,WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE|WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN,PixelFormat.TRANSLUCENT);
            layer.setOnTouchListener((view,event)->{
                if(event.getAction()==android.view.MotionEvent.ACTION_UP){
                    float x=event.getRawX()/metrics.widthPixels,y=event.getRawY()/metrics.heightPixels;
                    Store.prefs.edit().putFloat("point_"+key+"_x",x).putFloat("point_"+key+"_y",y).apply();
                    windows.removeView(layer);Store.state(label+"位置已保存");openHome();
                }return true;
            });windows.addView(layer,params);
        },700);
    }
}
