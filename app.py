from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

import pandas as pd
import requests
import streamlit as st


st.set_page_config(page_title="全国天气看板", page_icon="🌦️", layout="wide")
st.markdown(
    """
    <style>
    .block-container {max-width: 1500px; padding-top: 1.5rem;}
    [data-testid="stMetric"] {background:#102235; border:1px solid #29445d; padding:14px 16px; border-radius:14px;}
    .rain-now {color:#4fc3f7; font-weight:700;}
    .rain-risk {color:#ffbd59; font-weight:700;}
    </style>
    """,
    unsafe_allow_html=True,
)

TZ = ZoneInfo("Asia/Shanghai")
API = "https://api.open-meteo.com/v1/forecast"
RAIN_CODES = {51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82, 95, 96, 99}
WEATHER = {
    0: "晴", 1: "晴间多云", 2: "多云", 3: "阴", 45: "雾", 48: "雾凇",
    51: "毛毛雨", 53: "小雨", 55: "中雨", 56: "冻毛毛雨", 57: "冻毛毛雨",
    61: "小雨", 63: "中雨", 65: "大雨", 66: "冻雨", 67: "冻雨",
    71: "小雪", 73: "中雪", 75: "大雪", 77: "雪粒", 80: "阵雨",
    81: "强阵雨", 82: "暴雨", 85: "阵雪", 86: "强阵雪", 95: "雷雨",
    96: "雷雨伴冰雹", 99: "强雷雨伴冰雹",
}

# Nationwide city coordinates (same catalog as the HTML dashboard).
CITIES = [{"name":"阿坝藏族羌族自治州","lat":32.9,"lon":101.7,"region":"西南"},{"name":"阿克苏市","lat":41.17,"lon":80.27,"region":"西北"},{"name":"阿拉善盟","lat":38.83,"lon":105.67,"region":"华北"},{"name":"阿勒泰市","lat":47.85,"lon":88.13,"region":"西北"},{"name":"阿里市","lat":32.5,"lon":80.1,"region":"西南"},{"name":"安康市","lat":32.68,"lon":109.02,"region":"西北"},{"name":"安庆市","lat":30.53,"lon":117.05,"region":"华东"},{"name":"安顺市","lat":26.25,"lon":105.95,"region":"西南"},{"name":"安阳市","lat":36.1,"lon":114.38,"region":"华中"},{"name":"鞍山市","lat":41.1,"lon":122.98,"region":"东北"},{"name":"澳门特别行政区","lat":22.13,"lon":113.33,"region":"华南"},{"name":"巴彦淖尔市","lat":40.75,"lon":107.42,"region":"华北"},{"name":"巴音郭楞蒙古自治州","lat":41.77,"lon":86.15,"region":"西北"},{"name":"巴中市","lat":31.85,"lon":106.77,"region":"西南"},{"name":"白城市","lat":45.62,"lon":122.83,"region":"东北"},{"name":"白山市","lat":41.93,"lon":126.42,"region":"东北"},{"name":"白银市","lat":36.55,"lon":104.18,"region":"西北"},{"name":"百色市","lat":23.9,"lon":106.62,"region":"华南"},{"name":"蚌埠市","lat":32.92,"lon":117.38,"region":"华东"},{"name":"包头市","lat":40.65,"lon":109.83,"region":"华北"},{"name":"宝鸡市","lat":34.37,"lon":107.13,"region":"西北"},{"name":"保定市","lat":38.87,"lon":115.47,"region":"华北"},{"name":"保山市","lat":25.12,"lon":99.17,"region":"西南"},{"name":"北海市","lat":21.48,"lon":109.12,"region":"华南"},{"name":"北京市","lat":39.9,"lon":116.4,"region":"华北"},{"name":"本溪市","lat":41.3,"lon":123.77,"region":"东北"},{"name":"毕节市","lat":27.3,"lon":105.28,"region":"西南"},{"name":"滨州","lat":37.38,"lon":117.97,"region":"华东"},{"name":"亳州","lat":33.85,"lon":115.78,"region":"华中"},{"name":"博尔塔拉蒙古自治州","lat":44.9,"lon":82.07,"region":"西北"},{"name":"沧州","lat":38.3,"lon":116.83,"region":"华北"},{"name":"昌都市","lat":31.13,"lon":97.18,"region":"西南"},{"name":"昌吉市","lat":44.02,"lon":87.3,"region":"西北"},{"name":"常德市","lat":29.05,"lon":111.68,"region":"华中"},{"name":"常州","lat":31.78,"lon":119.95,"region":"华东"},{"name":"朝阳市","lat":41.58,"lon":120.47,"region":"东北"},{"name":"潮州","lat":23.67,"lon":116.62,"region":"华南"},{"name":"郴州","lat":25.78,"lon":113.02,"region":"华中"},{"name":"成都市","lat":30.67,"lon":104.07,"region":"西南"},{"name":"承德市","lat":40.97,"lon":117.93,"region":"华北"},{"name":"池州","lat":30.67,"lon":117.48,"region":"华东"},{"name":"赤峰市","lat":42.27,"lon":118.92,"region":"华北"},{"name":"重庆市","lat":29.57,"lon":106.55,"region":"西南"},{"name":"崇左市","lat":22.4,"lon":107.37,"region":"华南"},{"name":"滁州","lat":32.3,"lon":118.32,"region":"华东"},{"name":"楚雄彝族自治州","lat":25.03,"lon":101.55,"region":"西南"},{"name":"达州","lat":31.22,"lon":107.5,"region":"西南"},{"name":"大理白族自治州","lat":25.6,"lon":100.23,"region":"西南"},{"name":"大连市","lat":38.92,"lon":121.62,"region":"东北"},{"name":"大庆市","lat":46.58,"lon":125.03,"region":"东北"},{"name":"大同市","lat":40.09,"lon":113.3,"region":"华北"},{"name":"大兴安岭地区","lat":50.42,"lon":124.12,"region":"东北"},{"name":"丹东市","lat":40.13,"lon":124.38,"region":"东北"},{"name":"德宏傣族景颇族自治州","lat":24.43,"lon":98.58,"region":"西南"},{"name":"德阳市","lat":31.13,"lon":104.38,"region":"西南"},{"name":"德州","lat":37.45,"lon":116.3,"region":"华东"},{"name":"迪庆藏族自治州","lat":27.83,"lon":99.7,"region":"西南"},{"name":"定西市","lat":35.58,"lon":104.62,"region":"西北"},{"name":"东莞市","lat":23.05,"lon":113.75,"region":"华南"},{"name":"东营市","lat":37.43,"lon":118.67,"region":"华东"},{"name":"鄂尔多斯市","lat":39.62,"lon":109.8,"region":"华北"},{"name":"鄂州","lat":30.4,"lon":114.88,"region":"华中"},{"name":"恩施土家族苗族自治州","lat":30.3,"lon":109.47,"region":"华中"},{"name":"防城港市","lat":21.7,"lon":108.35,"region":"华南"},{"name":"佛山市","lat":23.02,"lon":113.12,"region":"华南"},{"name":"福州","lat":26.08,"lon":119.3,"region":"华东"},{"name":"抚顺市","lat":41.88,"lon":123.9,"region":"东北"},{"name":"抚州","lat":28,"lon":116.35,"region":"华东"},{"name":"阜新市","lat":42.07,"lon":121.75,"region":"东北"},{"name":"阜阳市","lat":32.9,"lon":115.82,"region":"华东"},{"name":"甘南藏族自治州","lat":34.983,"lon":102.911,"region":"西北"},{"name":"甘孜市","lat":30.05,"lon":101.97,"region":"西南"},{"name":"赣州","lat":25.83,"lon":114.93,"region":"华东"},{"name":"固原市","lat":36,"lon":106.28,"region":"西北"},{"name":"广安市","lat":30.47,"lon":106.63,"region":"西南"},{"name":"广元市","lat":32.43,"lon":105.83,"region":"西南"},{"name":"广州","lat":23.13,"lon":113.27,"region":"华南"},{"name":"贵港市","lat":23.1,"lon":109.6,"region":"华南"},{"name":"贵阳市","lat":26.65,"lon":106.63,"region":"西南"},{"name":"桂林市","lat":25.28,"lon":110.28,"region":"华南"},{"name":"果洛藏族自治州","lat":34.48,"lon":100.23,"region":"西北"},{"name":"哈尔滨市","lat":45.8,"lon":126.53,"region":"东北"},{"name":"哈密市","lat":42.83,"lon":93.52,"region":"西北"},{"name":"海北藏族自治州","lat":36.97,"lon":100.9,"region":"西北"},{"name":"海东市","lat":36.5,"lon":102.12,"region":"西北"},{"name":"海口市","lat":20.03,"lon":110.32,"region":"华南"},{"name":"海南藏族自治州","lat":36.28,"lon":100.62,"region":"西北"},{"name":"海西蒙古族藏族自治州","lat":37.37,"lon":97.37,"region":"西北"},{"name":"邯郸市","lat":36.62,"lon":114.48,"region":"华北"},{"name":"汉中市","lat":33.07,"lon":107.02,"region":"西北"},{"name":"杭州","lat":30.28,"lon":120.15,"region":"华东"},{"name":"合肥市","lat":31.83,"lon":117.25,"region":"华东"},{"name":"和田市","lat":37.12,"lon":79.92,"region":"西北"},{"name":"河池市","lat":24.7,"lon":108.07,"region":"华南"},{"name":"河源市","lat":23.73,"lon":114.7,"region":"华南"},{"name":"菏泽市","lat":35.26,"lon":115.585,"region":"华东"},{"name":"贺州","lat":24.42,"lon":111.55,"region":"华南"},{"name":"鹤壁市","lat":35.75,"lon":114.28,"region":"华中"},{"name":"鹤岗市","lat":47.33,"lon":130.27,"region":"东北"},{"name":"黑河市","lat":50.25,"lon":127.48,"region":"东北"},{"name":"衡水市","lat":37.73,"lon":115.68,"region":"华北"},{"name":"衡阳市","lat":26.9,"lon":112.57,"region":"华中"},{"name":"红河哈尼族彝族自治州","lat":23.37,"lon":103.4,"region":"西南"},{"name":"呼和浩特市","lat":40.83,"lon":111.73,"region":"华北"},{"name":"呼伦贝尔市","lat":49.22,"lon":119.77,"region":"华北"},{"name":"湖州","lat":30.9,"lon":120.08,"region":"华东"},{"name":"葫芦岛市","lat":40.72,"lon":120.83,"region":"东北"},{"name":"怀化市","lat":27.57,"lon":110,"region":"华中"},{"name":"淮安市","lat":33.62,"lon":119.02,"region":"华东"},{"name":"淮北市","lat":33.95,"lon":116.8,"region":"华东"},{"name":"淮南市","lat":32.63,"lon":117,"region":"华东"},{"name":"黄冈市","lat":30.45,"lon":114.87,"region":"华中"},{"name":"黄南藏族自治州","lat":35.52,"lon":102.02,"region":"西北"},{"name":"黄山市","lat":29.72,"lon":118.33,"region":"华东"},{"name":"黄石市","lat":30.2,"lon":115.03,"region":"华中"},{"name":"惠州","lat":23.12,"lon":114.42,"region":"华南"},{"name":"鸡西市","lat":45.3,"lon":130.97,"region":"东北"},{"name":"吉安市","lat":27.05,"lon":114.9,"region":"华东"},{"name":"吉林市","lat":43.83,"lon":126.55,"region":"东北"},{"name":"济南市","lat":36.67,"lon":116.98,"region":"华东"},{"name":"济宁市","lat":35.42,"lon":116.58,"region":"华东"},{"name":"佳木斯市","lat":46.82,"lon":130.37,"region":"东北"},{"name":"嘉兴市","lat":30.75,"lon":120.75,"region":"华东"},{"name":"嘉峪关市","lat":39.8,"lon":98.27,"region":"西北"},{"name":"江门市","lat":22.58,"lon":113.08,"region":"华南"},{"name":"焦作市","lat":35.22,"lon":113.25,"region":"华中"},{"name":"揭阳市","lat":23.55,"lon":116.37,"region":"华南"},{"name":"金昌市","lat":38.5,"lon":102.18,"region":"西北"},{"name":"金华市","lat":29.08,"lon":119.65,"region":"华东"},{"name":"金门市","lat":24.43,"lon":118.32,"region":"华东"},{"name":"锦州","lat":41.1,"lon":121.13,"region":"东北"},{"name":"晋城市","lat":35.5,"lon":112.83,"region":"华中"},{"name":"晋中市","lat":37.68,"lon":112.75,"region":"华北"},{"name":"荆门市","lat":31.03,"lon":112.2,"region":"华中"},{"name":"荆州","lat":30.33,"lon":112.23,"region":"华中"},{"name":"景德镇市","lat":29.27,"lon":117.17,"region":"华东"},{"name":"九江市","lat":29.62,"lon":115.88,"region":"华东"},{"name":"酒泉市","lat":39.75,"lon":98.52,"region":"西北"},{"name":"喀什市","lat":39.47,"lon":75.98,"region":"西北"},{"name":"开封市","lat":34.8,"lon":114.3,"region":"华中"},{"name":"克拉玛依市","lat":45.6,"lon":84.87,"region":"西北"},{"name":"克孜勒苏柯尔克孜自治州","lat":39.76,"lon":76.205,"region":"西北"},{"name":"昆明市","lat":25.05,"lon":102.72,"region":"西南"},{"name":"拉萨市","lat":29.65,"lon":91.13,"region":"西南"},{"name":"来宾市","lat":23.73,"lon":109.23,"region":"华南"},{"name":"兰州","lat":36.07,"lon":103.82,"region":"西北"},{"name":"廊坊市","lat":39.52,"lon":116.7,"region":"华北"},{"name":"乐山市","lat":29.57,"lon":103.77,"region":"西南"},{"name":"丽江市","lat":26.88,"lon":100.23,"region":"西南"},{"name":"丽水市","lat":28.45,"lon":119.92,"region":"华东"},{"name":"连江市","lat":26.2,"lon":119.53,"region":"华东"},{"name":"连云港市","lat":34.6,"lon":119.22,"region":"华东"},{"name":"凉山彝族自治州","lat":27.9,"lon":102.27,"region":"西南"},{"name":"辽阳市","lat":41.22,"lon":123.07,"region":"东北"},{"name":"辽源市","lat":42.88,"lon":125.13,"region":"东北"},{"name":"聊城市","lat":36.45,"lon":115.98,"region":"华东"},{"name":"林芝市","lat":29.68,"lon":94.37,"region":"西南"},{"name":"临沧市","lat":23.88,"lon":100.08,"region":"西南"},{"name":"临汾市","lat":36.08,"lon":111.52,"region":"华北"},{"name":"临夏市","lat":35.5,"lon":103,"region":"西北"},{"name":"临沂市","lat":35.05,"lon":118.35,"region":"华东"},{"name":"柳州","lat":24.33,"lon":109.42,"region":"华南"},{"name":"六安市","lat":31.77,"lon":116.5,"region":"华东"},{"name":"六盘水市","lat":26.6,"lon":104.83,"region":"西南"},{"name":"龙岩市","lat":25.1,"lon":117.03,"region":"华东"},{"name":"陇南市","lat":33.4,"lon":104.92,"region":"西北"},{"name":"娄底市","lat":27.73,"lon":112,"region":"华中"},{"name":"泸州","lat":28.87,"lon":105.43,"region":"西南"},{"name":"吕梁市","lat":37.52,"lon":111.13,"region":"华北"},{"name":"洛阳市","lat":34.62,"lon":112.45,"region":"华中"},{"name":"漯河市","lat":33.58,"lon":114.02,"region":"华中"},{"name":"马鞍山市","lat":31.7,"lon":118.5,"region":"华东"},{"name":"茂名市","lat":21.67,"lon":110.92,"region":"华南"},{"name":"眉山市","lat":30.05,"lon":103.83,"region":"西南"},{"name":"梅州","lat":24.28,"lon":116.12,"region":"华南"},{"name":"绵阳市","lat":31.47,"lon":104.73,"region":"西南"},{"name":"牡丹江市","lat":44.58,"lon":129.6,"region":"东北"},{"name":"那曲市","lat":31.48,"lon":92.07,"region":"西南"},{"name":"南昌市","lat":28.68,"lon":115.85,"region":"华东"},{"name":"南充市","lat":30.78,"lon":106.08,"region":"西南"},{"name":"南京市","lat":32.07,"lon":118.78,"region":"华东"},{"name":"南宁市","lat":22.82,"lon":108.37,"region":"华南"},{"name":"南平市","lat":26.65,"lon":118.17,"region":"华东"},{"name":"南通市","lat":31.98,"lon":120.88,"region":"华东"},{"name":"内江市","lat":29.58,"lon":105.05,"region":"西南"},{"name":"宁德市","lat":26.67,"lon":119.52,"region":"华东"},{"name":"怒江傈僳族自治州","lat":25.85,"lon":98.85,"region":"西南"},{"name":"攀枝花市","lat":26.58,"lon":101.72,"region":"西南"},{"name":"盘锦市","lat":41.12,"lon":122.07,"region":"东北"},{"name":"平顶山市","lat":33.77,"lon":113.18,"region":"华中"},{"name":"平凉市","lat":35.55,"lon":106.67,"region":"西北"},{"name":"屏东市","lat":22.67,"lon":120.48,"region":"华东"},{"name":"萍乡市","lat":27.63,"lon":113.85,"region":"华东"},{"name":"莆田市","lat":25.43,"lon":119,"region":"华东"},{"name":"濮阳市","lat":35.77,"lon":115.03,"region":"华中"},{"name":"普洱市","lat":23.43,"lon":100.735,"region":"西南"},{"name":"七台河市","lat":45.78,"lon":130.95,"region":"东北"},{"name":"齐齐哈尔市","lat":47.33,"lon":123.95,"region":"东北"},{"name":"黔东南苗族侗族自治州","lat":26.58,"lon":107.97,"region":"西南"},{"name":"黔南布依族苗族自治州","lat":26.27,"lon":107.52,"region":"西南"},{"name":"黔西南布依族苗族自治州","lat":25.405,"lon":105.555,"region":"西南"},{"name":"钦州","lat":21.95,"lon":108.62,"region":"华南"},{"name":"秦皇岛市","lat":39.93,"lon":119.6,"region":"华北"},{"name":"青岛市","lat":36.07,"lon":120.38,"region":"华东"},{"name":"清远市","lat":23.7,"lon":113.03,"region":"华南"},{"name":"庆阳市","lat":35.73,"lon":107.63,"region":"西北"},{"name":"曲靖市","lat":25.5,"lon":103.8,"region":"西南"},{"name":"衢州","lat":28.93,"lon":118.87,"region":"华东"},{"name":"泉州","lat":24.88,"lon":118.67,"region":"华东"},{"name":"日喀则市","lat":29.27,"lon":88.88,"region":"西南"},{"name":"日照市","lat":35.42,"lon":119.52,"region":"华东"},{"name":"三门峡市","lat":34.78,"lon":111.2,"region":"华中"},{"name":"三明市","lat":26.27,"lon":117.62,"region":"华东"},{"name":"三亚市","lat":18.25,"lon":109.5,"region":"华南"},{"name":"厦门市","lat":24.48,"lon":118.08,"region":"华东"},{"name":"山南市","lat":29.23,"lon":91.77,"region":"西南"},{"name":"汕头市","lat":23.35,"lon":116.68,"region":"华南"},{"name":"汕尾市","lat":22.78,"lon":115.37,"region":"华南"},{"name":"商洛市","lat":33.87,"lon":109.93,"region":"西北"},{"name":"商丘市","lat":34.45,"lon":115.65,"region":"华中"},{"name":"上海市","lat":31.23,"lon":121.47,"region":"华东"},{"name":"上饶市","lat":28.43,"lon":117.92,"region":"华东"},{"name":"韶关市","lat":24.82,"lon":113.6,"region":"华南"},{"name":"邵阳市","lat":27.25,"lon":111.47,"region":"华中"},{"name":"绍兴市","lat":30.08,"lon":120.47,"region":"华东"},{"name":"深圳市","lat":22.55,"lon":114.05,"region":"华南"},{"name":"沈阳市","lat":41.8,"lon":123.43,"region":"东北"},{"name":"十堰市","lat":32.65,"lon":110.78,"region":"华中"},{"name":"石家庄市","lat":38.05,"lon":114.52,"region":"华北"},{"name":"石嘴山市","lat":39.02,"lon":106.38,"region":"西北"},{"name":"双鸭山市","lat":46.63,"lon":131.15,"region":"东北"},{"name":"朔州","lat":39.33,"lon":112.43,"region":"华北"},{"name":"四平市","lat":43.17,"lon":124.35,"region":"东北"},{"name":"松原市","lat":45.13,"lon":124.82,"region":"东北"},{"name":"苏州","lat":31.3,"lon":120.58,"region":"华东"},{"name":"宿迁市","lat":33.97,"lon":118.28,"region":"华东"},{"name":"宿州","lat":33.63,"lon":116.98,"region":"华东"},{"name":"绥化市","lat":46.63,"lon":126.98,"region":"东北"},{"name":"随州","lat":31.72,"lon":113.37,"region":"华中"},{"name":"遂宁市","lat":30.52,"lon":105.57,"region":"西南"},{"name":"塔城市","lat":46.75,"lon":82.98,"region":"西北"},{"name":"台州","lat":28.68,"lon":121.43,"region":"华东"},{"name":"太原市","lat":37.87,"lon":112.55,"region":"华北"},{"name":"泰安市","lat":36.2,"lon":117.08,"region":"华东"},{"name":"泰州","lat":32.45,"lon":119.92,"region":"华东"},{"name":"唐山市","lat":39.63,"lon":118.2,"region":"华北"},{"name":"天津市","lat":39.12,"lon":117.2,"region":"华北"},{"name":"天水市","lat":34.58,"lon":105.72,"region":"西北"},{"name":"铁岭市","lat":42.3,"lon":123.83,"region":"东北"},{"name":"通化市","lat":41.73,"lon":125.93,"region":"东北"},{"name":"通辽市","lat":43.62,"lon":122.27,"region":"华北"},{"name":"铜川市","lat":34.9,"lon":108.93,"region":"西北"},{"name":"铜陵市","lat":30.95,"lon":117.78,"region":"华东"},{"name":"吐鲁番市","lat":42.95,"lon":89.17,"region":"西北"},{"name":"威海市","lat":37.52,"lon":122.12,"region":"华东"},{"name":"潍坊市","lat":36.7,"lon":119.15,"region":"华东"},{"name":"渭南市","lat":34.5,"lon":109.5,"region":"西北"},{"name":"温州","lat":28,"lon":120.7,"region":"华东"},{"name":"文山壮族苗族自治州","lat":23.37,"lon":104.25,"region":"西南"},{"name":"乌海市","lat":39.67,"lon":106.82,"region":"华北"},{"name":"乌兰察布市","lat":40.98,"lon":113.12,"region":"华北"},{"name":"乌鲁木齐市","lat":43.8,"lon":87.6,"region":"西北"},{"name":"无锡市","lat":31.57,"lon":120.3,"region":"华东"},{"name":"吴忠市","lat":37.98,"lon":106.2,"region":"西北"},{"name":"芜湖市","lat":31.15,"lon":118.57,"region":"华东"},{"name":"梧州","lat":23.48,"lon":111.27,"region":"华南"},{"name":"武汉市","lat":30.6,"lon":114.3,"region":"华中"},{"name":"武威市","lat":37.93,"lon":102.63,"region":"西北"},{"name":"西安市","lat":34.27,"lon":108.93,"region":"西北"},{"name":"西宁市","lat":36.62,"lon":101.78,"region":"西北"},{"name":"西双版纳傣族自治州","lat":22.02,"lon":100.8,"region":"西南"},{"name":"锡林郭勒盟","lat":43.95,"lon":116.07,"region":"华北"},{"name":"咸宁市","lat":29.85,"lon":114.32,"region":"华中"},{"name":"咸阳市","lat":34.33,"lon":108.7,"region":"西北"},{"name":"香港特别行政区","lat":22.2,"lon":114.08,"region":"华南"},{"name":"湘潭市","lat":27.78,"lon":112.95,"region":"华中"},{"name":"湘西土家族苗族自治州","lat":28.32,"lon":109.73,"region":"华中"},{"name":"襄阳市","lat":32.02,"lon":112.15,"region":"华中"},{"name":"孝感市","lat":30.93,"lon":113.92,"region":"华中"},{"name":"忻州","lat":38.42,"lon":112.73,"region":"华北"},{"name":"新乡市","lat":35.2,"lon":113.8,"region":"华中"},{"name":"新余市","lat":27.82,"lon":114.92,"region":"华东"},{"name":"信阳市","lat":32.13,"lon":114.07,"region":"华中"},{"name":"邢台市","lat":37.07,"lon":114.48,"region":"华北"},{"name":"兴安盟","lat":46.08,"lon":122.05,"region":"华北"},{"name":"徐州","lat":34.27,"lon":117.18,"region":"华东"},{"name":"许昌市","lat":34,"lon":113.83,"region":"华中"},{"name":"宣城市","lat":30.95,"lon":118.75,"region":"华东"},{"name":"雅安市","lat":29.98,"lon":103,"region":"西南"},{"name":"烟台市","lat":37.45,"lon":121.43,"region":"华东"},{"name":"延安市","lat":36.6,"lon":109.48,"region":"西北"},{"name":"延边朝鲜族自治州","lat":42.88,"lon":129.5,"region":"东北"},{"name":"盐城市","lat":33.35,"lon":120.15,"region":"华东"},{"name":"扬州","lat":32.4,"lon":119.4,"region":"华东"},{"name":"阳江市","lat":21.87,"lon":111.98,"region":"华南"},{"name":"阳泉市","lat":37.85,"lon":113.57,"region":"华北"},{"name":"伊春市","lat":47.73,"lon":128.9,"region":"东北"},{"name":"伊犁哈萨克自治州","lat":43.92,"lon":81.32,"region":"西北"},{"name":"宜宾市","lat":28.7,"lon":104.55,"region":"西南"},{"name":"宜昌市","lat":30.7,"lon":111.28,"region":"华中"},{"name":"宜春市","lat":27.8,"lon":114.38,"region":"华东"},{"name":"宜兰市","lat":24.77,"lon":121.75,"region":"华东"},{"name":"益阳市","lat":28.6,"lon":112.32,"region":"华中"},{"name":"银川市","lat":38.47,"lon":106.28,"region":"西北"},{"name":"鹰潭市","lat":28.27,"lon":117.07,"region":"华东"},{"name":"营口市","lat":40.67,"lon":122.23,"region":"东北"},{"name":"永州","lat":26.43,"lon":111.62,"region":"华中"},{"name":"榆林市","lat":38.28,"lon":109.73,"region":"西北"},{"name":"玉林市","lat":22.63,"lon":110.17,"region":"华南"},{"name":"玉树藏族自治州","lat":33,"lon":97.02,"region":"西北"},{"name":"玉溪市","lat":24.35,"lon":102.55,"region":"西南"},{"name":"岳阳市","lat":29.15,"lon":113.12,"region":"华中"},{"name":"云浮市","lat":22.92,"lon":112.03,"region":"华南"},{"name":"运城市","lat":35.02,"lon":110.98,"region":"西北"},{"name":"枣庄市","lat":34.82,"lon":117.32,"region":"华东"},{"name":"湛江市","lat":21.27,"lon":110.35,"region":"华南"},{"name":"张家界市","lat":29.13,"lon":110.47,"region":"华中"},{"name":"张家口市","lat":40.82,"lon":114.88,"region":"华北"},{"name":"张掖市","lat":38.93,"lon":100.45,"region":"西北"},{"name":"漳州","lat":24.52,"lon":117.65,"region":"华东"},{"name":"长春市","lat":43.9,"lon":125.32,"region":"东北"},{"name":"长沙市","lat":28.23,"lon":112.93,"region":"华中"},{"name":"长治市","lat":36.05,"lon":113.03,"region":"华中"},{"name":"昭通市","lat":27.33,"lon":103.72,"region":"西南"},{"name":"肇庆市","lat":23.05,"lon":112.47,"region":"华南"},{"name":"镇江市","lat":32.2,"lon":119.45,"region":"华东"},{"name":"郑州","lat":34.75,"lon":113.62,"region":"华中"},{"name":"中山市","lat":22.517,"lon":113.3926,"region":"华南"},{"name":"中卫市","lat":37.52,"lon":105.18,"region":"西北"},{"name":"舟山市","lat":30,"lon":122.2,"region":"华东"},{"name":"周口市","lat":33.62,"lon":114.65,"region":"华中"},{"name":"株洲市","lat":27.72,"lon":113.13,"region":"华中"},{"name":"珠海市","lat":22.27,"lon":113.57,"region":"华南"},{"name":"驻马店市","lat":32.98,"lon":114.02,"region":"华中"},{"name":"资阳市","lat":30.1286,"lon":104.6276,"region":"西南"},{"name":"淄博市","lat":36.82,"lon":118.05,"region":"华东"},{"name":"自贡市","lat":29.35,"lon":104.78,"region":"西南"},{"name":"遵义市","lat":27.73,"lon":106.92,"region":"西南"}]


def update_slot(now: datetime) -> str:
    """One shared API refresh slot per morning/evening window, China time."""
    today = now.date()
    morning = now.replace(hour=8, minute=30, second=0, microsecond=0)
    evening = now.replace(hour=17, minute=0, second=0, microsecond=0)
    if now >= evening:
        return f"{today.isoformat()}-pm"
    if now >= morning:
        return f"{today.isoformat()}-am"
    return f"{(today - timedelta(days=1)).isoformat()}-pm"


@st.cache_data(show_spinner=False, max_entries=8)
def load_weather(slot: str) -> dict[str, dict]:
    """Fetch city forecasts once per scheduled slot; cache is shared across sessions."""
    result: dict[str, dict] = {}
    session = requests.Session()
    for start in range(0, len(CITIES), 35):
        batch = CITIES[start : start + 35]
        params = {
            "latitude": ",".join(str(city["lat"]) for city in batch),
            "longitude": ",".join(str(city["lon"]) for city in batch),
            "current": "temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,wind_speed_10m,precipitation",
            "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,precipitation_sum",
            "forecast_days": 16,
            "timezone": "Asia/Shanghai",
        }
        try:
            response = session.get(API, params=params, timeout=45)
            response.raise_for_status()
            payload = response.json()
            rows = payload if isinstance(payload, list) else [payload]
            for city, data in zip(batch, rows):
                if data.get("daily"):
                    result[city["name"]] = {"current": data.get("current", {}), "daily": data["daily"]}
        except (requests.RequestException, ValueError) as exc:
            st.warning(f"{batch[0]['name']} 至 {batch[-1]['name']} 这一批天气数据暂时无法获取：{exc}")
    return result


def is_raining_now(pack: Optional[dict]) -> bool:
    return bool(pack and int(pack.get("current", {}).get("weather_code", -1)) in RAIN_CODES)


def day_rain(pack: Optional[dict], index: int) -> bool:
    if not pack:
        return False
    daily = pack["daily"]
    code = int(daily.get("weather_code", [0])[index] or 0)
    probability = int(daily.get("precipitation_probability_max", [0] * 16)[index] or 0)
    amount = float(daily.get("precipitation_sum", [0] * 16)[index] or 0)
    return code in RAIN_CODES or probability >= 30 or amount >= 0.1


def rain_probability(pack: Optional[dict], days: int = 1) -> int:
    if not pack:
        return 0
    values = pack["daily"].get("precipitation_probability_max", [])[:days]
    return max((int(value or 0) for value in values), default=0)


def rain_amount(pack: Optional[dict], index: int = 0) -> float:
    if not pack:
        return 0.0
    values = pack["daily"].get("precipitation_sum", [])
    return float(values[index] or 0) if index < len(values) else 0.0


now = datetime.now(TZ)
slot = update_slot(now)
st.title("🌦️ 全国天气看板")
st.caption(f"天气数据：Open-Meteo · 每天按北京时间 08:30 / 17:00 刷新时次 · 当前数据时次：{slot}")

with st.sidebar:
    st.header("筛选城市")
    regions = ["全部地区"] + sorted({city["region"] for city in CITIES})
    selected_region = st.selectbox("地区", regions)
    rain_mode = st.selectbox("降雨情况", ["全部城市（有雨优先）", "当前正在下雨", "今日有雨可能", "未来 3 天有雨可能"])
    city_query = st.text_input("城市搜索", placeholder="输入城市名称")
    st.caption("有雨可能：天气现象为降水、降水概率 ≥30% 或预报降水 ≥0.1 mm。")
    if st.button("重新获取天气", use_container_width=True):
        load_weather.clear()
        st.rerun()

with st.spinner("正在获取全国城市天气…"):
    weather = load_weather(slot)

current_rain_count = sum(is_raining_now(weather.get(city["name"])) for city in CITIES)
today_rain_count = sum(day_rain(weather.get(city["name"]), 0) for city in CITIES)
three_day_rain_count = sum(any(day_rain(weather.get(city["name"]), day) for day in range(3)) for city in CITIES)

summary = st.columns(3)
summary[0].metric("当前正在下雨", f"{current_rain_count} 个城市")
summary[1].metric("今日有雨可能", f"{today_rain_count} 个城市")
summary[2].metric("未来 3 天有雨可能", f"{three_day_rain_count} 个城市")

if not weather:
    st.error("暂时没有获取到天气数据，请稍后重试。")
    st.stop()

city_by_name = {city["name"]: city for city in CITIES}
if rain_mode == "当前正在下雨":
    names = [name for name, pack in weather.items() if is_raining_now(pack)]
elif rain_mode == "今日有雨可能":
    names = [name for name, pack in weather.items() if day_rain(pack, 0)]
elif rain_mode == "未来 3 天有雨可能":
    names = [name for name, pack in weather.items() if any(day_rain(pack, day) for day in range(3))]
else:
    names = list(weather)

if selected_region != "全部地区":
    names = [name for name in names if city_by_name[name]["region"] == selected_region]
if city_query.strip():
    names = [name for name in names if city_query.strip() in name]

def rain_rank(name: str) -> tuple[int, int, str]:
    pack = weather[name]
    rank = 3 if is_raining_now(pack) else 2 if day_rain(pack, 0) else 1 if any(day_rain(pack, i) for i in range(3)) else 0
    return (-rank, -rain_probability(pack, 3), name)

names.sort(key=rain_rank)
st.subheader(f"全国城市天气 · {len(names)} / {len(CITIES)} 个城市")

if not names:
    st.info("当前筛选条件下没有匹配城市。")
else:
    card_columns = st.columns(4)
    for index, name in enumerate(names):
        pack = weather[name]
        current = pack["current"]
        daily = pack["daily"]
        raining = is_raining_now(pack)
        risk = day_rain(pack, 0)
        condition = WEATHER.get(int(current.get("weather_code", -1)), "天气")
        badge = "🌧️ 正在下雨" if raining else "🌧️ 今日有雨可能" if risk else "☁️ 今日无明显降雨"
        with card_columns[index % 4]:
            with st.container(border=True):
                st.markdown(f"**{name}**　`{city_by_name[name]['region']}`")
                st.markdown(f"## {round(float(current.get('temperature_2m', 0)))}°　{condition}")
                st.markdown(f"**{badge}**")
                st.caption(
                    f"今日雨概率 {rain_probability(pack)}% · 预计 {rain_amount(pack):.1f} mm · "
                    f"未来3天最高 {rain_probability(pack, 3)}%"
                )
                if st.button("看 16 天预报", key=f"select-{name}", use_container_width=True):
                    st.session_state["forecast_city"] = name

forecast_city = st.session_state.get("forecast_city", "中山市")
if forecast_city not in weather:
    forecast_city = names[0] if names else next(iter(weather))

st.divider()
st.subheader(f"未来 16 天预报 · {forecast_city}")
selected_pack = weather[forecast_city]
selected_daily = selected_pack["daily"]
forecast_rows = []
for index, day in enumerate(selected_daily.get("time", [])):
    forecast_rows.append(
        {
            "日期": day,
            "天气": WEATHER.get(int(selected_daily["weather_code"][index]), "天气"),
            "最高温": f"{round(selected_daily['temperature_2m_max'][index])}°",
            "最低温": f"{round(selected_daily['temperature_2m_min'][index])}°",
            "降雨概率": f"{int(selected_daily.get('precipitation_probability_max', [0] * 16)[index] or 0)}%",
            "预计降水": f"{float(selected_daily.get('precipitation_sum', [0] * 16)[index] or 0):.1f} mm",
        }
    )
st.dataframe(pd.DataFrame(forecast_rows), hide_index=True, use_container_width=True)

st.caption(
    "说明：Open-Meteo 为数值天气模型数据，不等同于气象站实况。社区云端应用只会在有访问/运行时执行；"
    "每天两个时次会在应用下一次运行时切换，不能保证应用休眠期间后台准点请求。"
)
