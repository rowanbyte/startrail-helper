package cn.startrail.helper;

import android.graphics.*;
import java.util.*;

/** Small UI-text templates supplement OCR; no game scenery is compared. */
final class TextTemplates {
    record Mask(int width,int height,int[] pixels,float threshold){}
    static ArrayList<Mask> rewards;
    static Rect rewardHeading(Bitmap bitmap){
        if(rewards==null){
            rewards=new ArrayList<>();
            for(String asset:new String[]{"reward_heading.png","reward_heading_android.png"})try(java.io.InputStream in=Store.context.getAssets().open(asset)){
                Bitmap source=BitmapFactory.decodeStream(in);
                for(int width:new int[]{80,88,96,104,108,111,114,128,144}){
                    int height=Math.max(1,source.getHeight()*width/source.getWidth());
                    Bitmap scaled=Bitmap.createScaledBitmap(source,Math.max(1,width/3),Math.max(1,height/3),true);
                    int[] pixels=new int[scaled.getWidth()*scaled.getHeight()];scaled.getPixels(pixels,0,scaled.getWidth(),0,0,scaled.getWidth(),scaled.getHeight());
                    for(int i=0;i<pixels.length;i++)pixels[i]=Vision.gray(pixels[i]);
                    rewards.add(new Mask(scaled.getWidth(),scaled.getHeight(),pixels,asset.contains("android")?.71f:.78f));scaled.recycle();
                }source.recycle();
            }catch(Exception ignored){}
        }
        int left=(int)(bitmap.getWidth()*.085f),top=(int)(bitmap.getHeight()*.22f);
        int width=(int)(bitmap.getWidth()*.19f)/3,height=(int)(bitmap.getHeight()*.40f)/3;
        int[] pixels=new int[width*height];
        for(int y=0;y<height;y++)for(int x=0;x<width;x++)pixels[y*width+x]=Vision.gray(bitmap.getPixel(left+x*3,top+y*3));
        for(Mask mask:rewards){
            int templateInk=0;for(int value:mask.pixels)if(value<190)templateInk++;
            for(int y=0;y<=height-mask.height;y++)for(int x=0;x<=width-mask.width;x++){
                int candidateInk=0,overlap=0,delta=0;
                for(int ty=0;ty<mask.height;ty++)for(int tx=0;tx<mask.width;tx++){
                    int a=pixels[(y+ty)*width+x+tx],b=mask.pixels[ty*mask.width+tx];
                    if(a<190)candidateInk++;if(a<190&&b<190)overlap++;delta+=Math.abs(a-b);
                }
                float similarity=2f*overlap/Math.max(1,templateInk+candidateInk);
                if(similarity>mask.threshold&&delta/(float)mask.pixels.length<30)
                    return new Rect(left+x*3,top+y*3,left+(x+mask.width)*3,top+(y+mask.height)*3);
            }
        }return null;
    }
}
