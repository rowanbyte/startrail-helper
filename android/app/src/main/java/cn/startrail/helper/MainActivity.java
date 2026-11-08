package cn.startrail.helper;

import android.app.*;
import android.content.*;
import android.content.res.ColorStateList;
import android.graphics.*;
import android.graphics.drawable.GradientDrawable;
import android.os.*;
import android.provider.Settings;
import android.view.*;
import android.widget.*;
import java.io.File;
import java.util.*;

public final class MainActivity extends Activity {
    static final int BG=0xff0b1020,CARD=0xff151f35,INPUT=0xff0e172a,TEXT=0xffedf2ff,MUTED=0xff9eacc8,ACCENT=0xffa18aff,GREEN=0xff45dcb8;
    final Handler handler=new Handler(Looper.getMainLooper());
    LinearLayout list,root;
    TextView status,detail,permission,log,quota;
    Button flowerTab,legendTab;
    EditText count,slot;
    Spinner resources;
    String category="flowers",selectedId="",listKey="",lastLog="";
    boolean rebuilding=false;
    int selectedColor=ACCENT;
    final Runnable updater=new Runnable(){public void run(){update();handler.postDelayed(this,700);}};

    @Override public void onCreate(Bundle state){
        super.onCreate(state);Store.init(this);getWindow().setStatusBarColor(BG);getWindow().setNavigationBarColor(BG);
        Models.Config c=Store.config();category=c.category;selectedId=c.targetId;
        build();count.setText(String.valueOf(c.runs));slot.setText(String.valueOf(c.slot));setResources(c.resource);
        if(getIntent().getBooleanExtra("selftest",false)&&(getApplicationInfo().flags&android.content.pm.ApplicationInfo.FLAG_DEBUGGABLE)!=0)selfTest();
    }
    @Override protected void onResume(){super.onResume();GameAccessibilityService service=GameAccessibilityService.instance;if(service!=null&&Store.active&&!Store.paused)service.engine.pause("已打开助手，点击继续后返回游戏");handler.post(updater);}
    @Override protected void onPause(){handler.removeCallbacks(updater);super.onPause();}
    int dp(float n){return Math.round(n*getResources().getDisplayMetrics().density);}
    TextView text(String value,int sp,int color){TextView t=new TextView(this);t.setText(value);t.setTextSize(sp);t.setTextColor(color);return t;}
    GradientDrawable background(int color,int border){GradientDrawable d=new GradientDrawable();d.setColor(color);d.setCornerRadius(dp(16));if(border!=0)d.setStroke(dp(1),border);return d;}
    LinearLayout card(LinearLayout parent){LinearLayout box=new LinearLayout(this);box.setOrientation(LinearLayout.VERTICAL);box.setPadding(dp(20),dp(16),dp(20),dp(16));box.setBackground(background(CARD,0xff293650));LinearLayout.LayoutParams p=new LinearLayout.LayoutParams(-1,-2);p.setMargins(0,dp(12),0,0);parent.addView(box,p);return box;}
    Button button(String label,int color,View.OnClickListener listener){Button b=new Button(this);b.setText(label);b.setTextSize(14);b.setAllCaps(false);b.setTextColor(color==ACCENT?0xff101426:TEXT);b.setBackgroundTintList(ColorStateList.valueOf(color));b.setOnClickListener(listener);b.setMinHeight(dp(48));return b;}
    void gap(LinearLayout box,int height){View v=new View(this);box.addView(v,new LinearLayout.LayoutParams(1,dp(height)));}
    void build(){
        ScrollView scroll=new ScrollView(this);scroll.setFillViewport(true);scroll.setBackgroundColor(BG);setContentView(scroll);
        root=new LinearLayout(this);root.setOrientation(LinearLayout.VERTICAL);root.setPadding(dp(24),dp(24),dp(24),dp(30));scroll.addView(root);
        TextView title=text("✦  星轨助手",30,TEXT);title.setTypeface(null,Typeface.BOLD);root.addView(title);
        root.addView(text("安卓本地运行  ·  实时识别  ·  自动挑战",13,MUTED));
        LinearLayout permissions=card(root);permission=text("正在检查无障碍服务…",16,GREEN);permissions.addView(permission);
        gap(permissions,6);permissions.addView(text("允许读取游戏画面并执行触摸。识别与日志保存在本机，离开游戏后暂停操作。",12,MUTED));
        LinearLayout actions=new LinearLayout(this);permissions.addView(actions);actions.addView(button("启用无障碍",ACCENT,v->startActivity(new Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS))),new LinearLayout.LayoutParams(0,dp(52),1));
        actions.addView(button("打开游戏",0xff293750,v->openGame()),new LinearLayout.LayoutParams(0,dp(52),1));
        LinearLayout tabs=new LinearLayout(this);gap(root,15);root.addView(tabs);
        flowerTab=button("✿  稀兽花种",ACCENT,v->switchCategory("flowers"));legendTab=button("★  传说精灵",0xff293750,v->switchCategory("legends"));
        tabs.addView(flowerTab,new LinearLayout.LayoutParams(0,dp(55),1));tabs.addView(legendTab,new LinearLayout.LayoutParams(0,dp(55),1));
        LinearLayout progress=card(root);status=text(Store.status,17,GREEN);status.setTypeface(null,Typeface.BOLD);progress.addView(status);detail=text(Store.detail,12,MUTED);progress.addView(detail);
        LinearLayout settings=card(root);settings.addView(text("连刷设置",19,TEXT));
        LinearLayout settingsRow=new LinearLayout(this);settingsRow.setGravity(Gravity.CENTER_VERTICAL);settings.addView(settingsRow);
        settingsRow.addView(text("次数  ",14,MUTED));count=numberInput("2");settingsRow.addView(count,new LinearLayout.LayoutParams(dp(80),dp(52)));
        settingsRow.addView(text("     出战位置  ",14,MUTED));slot=numberInput("5");settingsRow.addView(slot,new LinearLayout.LayoutParams(dp(80),dp(52)));
        gap(settings,10);settings.addView(text("捕捉消耗",13,MUTED));resources=new Spinner(this);settings.addView(resources,new LinearLayout.LayoutParams(-1,dp(48)));
        quota=text("",12,MUTED);settings.addView(quota);
        settings.addView(text("燃薪虫：引燃 → 充分燃烧循环，能量不足时聚能。单宠力竭后最多等 2 分钟；失败记录后继续下一轮。",12,MUTED));
        LinearLayout controls=new LinearLayout(this);settings.addView(controls);
        controls.addView(button("开始连刷",ACCENT,v->startRun()),new LinearLayout.LayoutParams(0,dp(54),1));
        controls.addView(button("暂停 / 继续",0xff293750,v->{GameAccessibilityService s=service();if(s!=null){if(Store.paused)s.engine.resume();else s.engine.pause("已手动暂停");}}),new LinearLayout.LayoutParams(0,dp(54),1));
        controls.addView(button("停止",0xff543348,v->{GameAccessibilityService s=GameAccessibilityService.instance;if(s!=null)s.engine.stop("已手动停止");}),new LinearLayout.LayoutParams(0,dp(54),1));
        LinearLayout targets=card(root);LinearLayout heading=new LinearLayout(this);heading.setGravity(Gravity.CENTER_VERTICAL);targets.addView(heading);
        heading.addView(text("实时目标列表",19,TEXT),new LinearLayout.LayoutParams(0,-2,1));heading.addView(button("↻ 读取当前列表",0xff293750,v->{GameAccessibilityService s=service();if(s!=null){selectedId="";s.engine.scan(category);}}));
        targets.addView(text("先打开游戏并读取列表，再选择目标。每轮会重新定位当前卡片；目标下线时停止。",12,MUTED));
        list=new LinearLayout(this);list.setOrientation(LinearLayout.VERTICAL);targets.addView(list);
        LinearLayout advanced=card(root);advanced.addView(button("触摸位置校准",0xff293750,v->calibrate()));advanced.addView(button("传说玩法条件与资料",0xff293750,v->rules()));
        LinearLayout logs=card(root);logs.addView(text("运行日志",18,TEXT));log=text("尚无运行记录",12,MUTED);log.setTextIsSelectable(true);logs.addView(log);
        logs.addView(button("查看本次摘要",0xff293750,v->showSummary()));
        refreshTabs();renderTargets();
    }
    EditText numberInput(String value){EditText e=new EditText(this);e.setText(value);e.setSingleLine();e.setInputType(android.text.InputType.TYPE_CLASS_NUMBER);e.setTextColor(TEXT);e.setTextSize(16);e.setPadding(dp(12),0,dp(10),0);e.setBackground(background(INPUT,0xff354360));return e;}
    void switchCategory(String next){if(Store.active){toast("请先停止当前任务再切换模块");return;}if(category.equals(next))return;category=next;selectedId="";listKey="";setResources(category.equals("legends")?"blue":"purple");refreshTabs();renderTargets();}
    void refreshTabs(){flowerTab.setBackgroundTintList(ColorStateList.valueOf(category.equals("flowers")?ACCENT:0xff293750));legendTab.setBackgroundTintList(ColorStateList.valueOf(category.equals("legends")?ACCENT:0xff293750));}
    void setResources(String value){
        String[] labels=category.equals("legends")?new String[]{"蓝星 · 契约周次数","专用传说印记 · 不自动切换"}:new String[]{"优先紫星，不足时使用蓝星","优先蓝星，不足时使用紫星"};
        ArrayAdapter<String> adapter=new ArrayAdapter<>(this,android.R.layout.simple_spinner_item,labels);adapter.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item);resources.setAdapter(adapter);resources.setSelection(category.equals("legends")?(value.equals("legendary")?1:0):(value.equals("blue")?1:0));
    }
    void renderTargets(){
        list.removeAllViews();StringBuilder signature=new StringBuilder();int found=0;
        synchronized(Store.targets){for(Models.Target target:Store.targets){
            if(!target.category.equals(category))continue;found++;signature.append(target.id).append(';');
            LinearLayout row=new LinearLayout(this);row.setPadding(dp(10),dp(10),dp(10),dp(10));row.setGravity(Gravity.CENTER_VERTICAL);row.setBackground(background(target.id.equals(selectedId)?0xff303252:INPUT,target.id.equals(selectedId)?ACCENT:0xff263450));
            LinearLayout.LayoutParams margins=new LinearLayout.LayoutParams(-1,-2);margins.setMargins(0,dp(9),0,0);list.addView(row,margins);
            File thumbnail=new File(getFilesDir(),"target_"+Integer.toHexString(target.id.hashCode())+".png");
            if(thumbnail.exists()){Bitmap image=BitmapFactory.decodeFile(thumbnail.getAbsolutePath());ImageView preview=new ImageView(this);preview.setImageBitmap(image);preview.setScaleType(ImageView.ScaleType.CENTER_CROP);row.addView(preview,new LinearLayout.LayoutParams(dp(190),dp(72)));}
            TextView name=text(target.name,16,TEXT);name.setPadding(dp(12),0,dp(8),0);row.addView(name,new LinearLayout.LayoutParams(0,-2,1));
            row.addView(button(target.id.equals(selectedId)?"已选":"选择",target.id.equals(selectedId)?ACCENT:0xff293750,v->{selectedId=target.id;renderTargets();}));
        }}
        if(found==0){TextView empty=text("尚无目标。点击“读取当前列表”从游戏自动获取。",14,MUTED);empty.setPadding(0,dp(20),0,dp(20));list.addView(empty);}
        listKey=category+signature;
    }
    GameAccessibilityService service(){GameAccessibilityService s=GameAccessibilityService.instance;if(s==null){toast("请先在系统设置里启用“星轨助手”无障碍服务");return null;}return s;}
    void openGame(){GameAccessibilityService s=GameAccessibilityService.instance;if(s!=null)s.openGame();else{Intent launch=getPackageManager().getLaunchIntentForPackage(GameAccessibilityService.GAME);if(launch!=null)startActivity(launch);else toast("未找到游戏客户端");}}
    void startRun(){
        GameAccessibilityService s=service();if(s==null)return;
        int runs,position;try{runs=Integer.parseInt(count.getText().toString());position=Integer.parseInt(slot.getText().toString());}catch(NumberFormatException e){toast("请填写有效次数和出战位置");return;}
        if(runs<1||runs>100||position<1||position>6){toast("次数为 1—100，出战位置为 1—6");return;}
        Models.Target target=null;synchronized(Store.targets){for(Models.Target t:Store.targets)if(t.id.equals(selectedId))target=t;}
        if(target==null){toast("请先选择实时列表中的目标");return;}
        Models.Config config=new Models.Config();config.category=category;config.targetId=target.id;config.targetName=target.name;config.runs=runs;config.slot=position;
        config.resource=category.equals("legends")?(resources.getSelectedItemPosition()==0?"blue":"legendary"):(resources.getSelectedItemPosition()==0?"purple":"blue");s.engine.start(config);
    }
    void update(){
        permission.setText(GameAccessibilityService.instance==null?"○  无障碍尚未启用":"●  无障碍已连接 · 截图与触摸可用");
        permission.setTextColor(GameAccessibilityService.instance==null?0xffffbd72:GREEN);
        status.setText(Store.status);detail.setText((Store.active?("第 "+Store.round+" / "+Store.total+" 轮 · 成功 "+Store.succeeded+" · 失败 "+Store.failed+"\n"):"")+Store.detail);
        quota.setText(category.equals("legends")?"本周契约捕捉次数："+(Store.quota<0?"待读取":Store.quota+" / 3")+"；不会自动改用专用印记。":"两种星星互不限制；仅在确认优先资源不足时切换。");
        StringBuilder signature=new StringBuilder();synchronized(Store.targets){for(Models.Target t:Store.targets)if(t.category.equals(category))signature.append(t.id).append(';');}
        if(!listKey.equals(category+signature))renderTargets();
        String logs=Store.logText();if(!logs.equals(lastLog)){lastLog=logs;String[] lines=logs.split("\n");log.setText(String.join("\n",Arrays.copyOfRange(lines,Math.max(0,lines.length-35),lines.length)));}
    }
    void calibrate(){
        GameAccessibilityService s=service();if(s==null)return;
        String[] labels={"手册图标","移动摇杆中心","聚能按钮","逃跑按钮","蓝星选项","紫星 / 专用印记选项","本次专属球"};
        String[] keys={"manual","joystick","gather","flee","blue","other","ball"};
        new AlertDialog.Builder(this).setTitle("选择要校准的位置").setItems(labels,(dialog,index)->s.calibrate(keys[index],labels[index])).setNegativeButton("取消",null).show();
    }
    void rules(){
        String text="传说精灵与花种分别读取当前列表。\n\n契约印记路线按游戏本周计数控制；上限通常为 3 次，每次列表标注 40 蓝星。专用印记是另一支付方式，存在目标与库存限制，不能使用紫星替代。\n\n解锁依主线、赛季委托及账号晋升进度而异。帕尔资料要求精灵研究员；银月狼王等目标以当前任务锁定提示为准。\n\nS2 历史公告载明契约路线炫彩概率 3%，专用印记路线不再产出炫彩；当前概率以游戏公示为准。\n\n资源不足或无法确认时停止，不自动花费另一类专用印记。\n\n资料：\nwiki.biligame.com/nrc/龙息帕尔再临\nwiki.biligame.com/nrc/传说印记（物品）\nwww.youxiabc.com/p/45259.html";
        new AlertDialog.Builder(this).setTitle("传说精灵 · 条件与资源").setMessage(text).setPositiveButton("知道了",null).show();
    }
    void showSummary(){String value="尚无摘要";try{value=new String(java.nio.file.Files.readAllBytes(new File(getFilesDir(),"last_run.json").toPath()),java.nio.charset.StandardCharsets.UTF_8);}catch(Exception ignored){}new AlertDialog.Builder(this).setTitle("本地运行摘要").setMessage(value).setPositiveButton("关闭",null).show();}
    void toast(String message){Toast.makeText(this,message,Toast.LENGTH_LONG).show();}
    void selfTest(){new LocalSelfTest(this).run();}
}
