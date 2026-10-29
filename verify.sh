#!/bin/sh
# Isolated image-build self-test. Never mounted into or run against live media.
set -eu
php -r 'if(PHP_MAJOR_VERSION!==8||PHP_MINOR_VERSION!==5||!extension_loaded("mysqli")||!extension_loaded("gd")||!class_exists("DOMDocument")||!function_exists("proc_open")||!function_exists("posix_kill")||!function_exists("fsync"))exit(1);'
apache2ctl -t
apache2ctl -M 2>/dev/null | grep -q php_module
for tool in timeout flock setsid prlimit vips vipsheader; do command -v "$tool" >/dev/null; done
work=$(mktemp -d /tmp/lsnt-image-check.XXXXXXXX)
http=/var/www/html/lsnt-image-check.php
apache_pid=
cleanup() {
 if [ -n "$apache_pid" ]; then kill "$apache_pid" 2>/dev/null || true; wait "$apache_pid" 2>/dev/null || true; fi
 rm -rf "$work"
 rm -f "$http" /tmp/lsnt-verify.sh
}
trap cleanup EXIT HUP INT TERM
test ! -e "$http"
printf '%s\n' '<?php echo "LSNT_PHP_HTTP_OK";' > "$http"
apache2-foreground > "$work/apache.log" 2>&1 &
apache_pid=$!
ready=0
for attempt in 1 2 3 4 5 6 7 8 9 10; do
 if php -r 'exit(@file_get_contents("http://127.0.0.1/lsnt-image-check.php")==="LSNT_PHP_HTTP_OK"?0:1);'; then ready=1; break; fi
 sleep 1
done
test "$ready" = 1
vips black "$work/source.v" 513 257 --bands 3
vips pngsave "$work/source.v" "$work/input.png"
for pair in 'png png' 'jpeg jpg' 'tiff tif' 'jp2k jp2' 'webp webp'; do
 set -- $pair
 vips -l "${1}load" >/dev/null
 vips -l "${1}save" >/dev/null
 vips "${1}save" "$work/input.png" "$work/test.$2"
 vips "${1}load" "$work/test.$2" "$work/check.v"
 test "$(vipsheader -f width "$work/check.v")" = 513
 test "$(vipsheader -f height "$work/check.v")" = 257
done
vips dzsave "$work/input.png" "$work/map" --layout=dz --container=fs --tile-size=256 --overlap=1 --depth=onepixel '--suffix=.webp[Q=80]' --keep=none --vips-concurrency=2
php -r '
$root=$argv[1];$xml=new DOMDocument();if(!$xml->load($root."/map.dzi",LIBXML_NONET))exit(1);
$e=$xml->documentElement;if($e->getAttribute("TileSize")!=="256"||$e->getAttribute("Overlap")!=="1"||$e->getAttribute("Format")!=="webp")exit(2);
$w=513;$h=257;$levels=[];do{$levels[]=[$w,$h];if($w===1&&$h===1)break;$w=intdiv($w+1,2);$h=intdiv($h+1,2);}while(true);$levels=array_reverse($levels);$expected=0;
foreach($levels as $z=>[$w,$h])for($y=0;$y<intdiv($h+255,256);$y++)for($x=0;$x<intdiv($w+255,256);$x++){
 $p=$root."/map_files/$z/{$x}_{$y}.webp";$im=@imagecreatefromwebp($p);if(!$im)exit(3);
 $ew=min($w,($x+1)*256+1)-max(0,$x*256-1);$eh=min($h,($y+1)*256+1)-max(0,$y*256-1);
 if(imagesx($im)!==$ew||imagesy($im)!==$eh)exit(4);$expected++;
}
$props=$root."/map_files/vips-properties.xml";if(!is_file($props)||filesize($props)>65536)exit(5);
$raw=file_get_contents($props);if(stripos($raw,"<!DOCTYPE")!==false||stripos($raw,"<!ENTITY")!==false)exit(5);$pd=new DOMDocument();if(!$pd->loadXML($raw,LIBXML_NONET)||$pd->documentElement->namespaceURI!=="http://www.vips.ecs.soton.ac.uk//dzsave")exit(5);
$values=[];foreach($pd->getElementsByTagName("property")as $p){$n=$p->getElementsByTagName("name")->item(0);$v=$p->getElementsByTagName("value")->item(0);if(!$n||!$v)exit(5);$values[$n->textContent]=$v->textContent;}if(($values["width"]??null)!=="513"||($values["height"]??null)!=="257")exit(5);
$count=0;foreach(new RecursiveIteratorIterator(new RecursiveDirectoryIterator($root."/map_files",FilesystemIterator::SKIP_DOTS))as $f){if($f->getPathname()===$props)continue;if(!$f->isFile()||$f->getExtension()!=="webp")exit(5);$count++;}if($count!==$expected)exit(6);
$packages=shell_exec("dpkg-query -W -f=\x27\x24{binary:Package}\\t\x24{Version}\\n\x27");if(!is_string($packages))exit(7);
$report=json_encode(["php"=>PHP_VERSION,"apache"=>trim(shell_exec("apache2 -v")),"vips"=>trim(shell_exec("vips --version")),"packages"=>$packages,"codecs"=>["PNG","JPEG","TIFF","JPEG2000","WebP"],"q80_tiles"=>$count,"http_php"=>true],JSON_UNESCAPED_SLASHES|JSON_THROW_ON_ERROR);
if(file_put_contents("/usr/local/share/lostsurveyor-image/verification.json",$report."\n")!==strlen($report)+1)exit(8);
echo "LSNT_AUTO_REPORT=".$report."\n";
' "$work"
