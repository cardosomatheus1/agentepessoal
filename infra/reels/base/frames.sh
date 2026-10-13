# uso: frames.sh <video.mp4> <pasta_reel>  -> pasta/v/q0001.jpg… (câmera lenta 2x, 30 fps, 360 quadros)
mkdir -p "$2/v" && rm -f "$2"/v/*.jpg
ffmpeg -v error -y -i "$1" -vf "setpts=2*PTS,minterpolate=fps=30:mi_mode=mci:mc_mode=aobmc:vsbmc=1,scale=1280:720" -frames:v 360 -q:v 3 "$2/v/q%04d.jpg"
ls "$2/v" | wc -l
