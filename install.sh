main() {
    pacman -Sy --noconfirm git uv
    git clone https://github.com/HazelTheWitch/demeter.git
    exec uv --directory demeter run main.py
}

main
