import sh
from pathlib import Path
from sys import stdout
import json
import getpass


def header(header: str):
    print(f" -- {header} --")


def main():
    disk = input("Drive to install to: ")
    hostname = input("Hostname for new system: ")
    username = input("Username for new user: ")

    while True:
        password = getpass.getpass("Password for new user: ")

        if getpass.getpass("Repeat password: ") == password:
            break

    header(f"Partitioning {disk}")

    if sh.partprobe("-d", "-s", disk):
        if input(f"{disk} is not empty, do you want to overwrite? (y/N): ").lower() != "y":
            print("Aboring!")
            return

        sh.wipefs("-a", disk)

    working_dir = Path(__file__).parent

    with (working_dir / "partitioning.sfdisk").open() as partitioning:
        sh.sfdisk(disk, _in=partitioning, _out=stdout)

    disk_info = json.loads(sh.lsblk("-J", disk))

    partition_info = disk_info["blockdevices"][0]["children"]

    efi_partition = "/dev/" + partition_info[0]["name"]
    root_partition = "/dev/" + partition_info[1]["name"]

    header(f"Formatting {efi_partition}")
    sh.Command("mkfs.fat")("-F", "32", efi_partition, _out=stdout)
    
    header(f"Formatting {root_partition}")
    sh.Command("mkfs.btrfs")("-f", root_partition, _out=stdout)

    header("Creating BTRFS Subvolumes")
    sh.mount(root_partition, "/mnt")

    subvolumes = {
        "@": "/mnt",
        "@home": "/mnt/home",
        "@snapshots": "/mnt/.snapshots",
        "@var_log": "/mnt/var/log",
    }

    for subvolume in subvolumes:
        sh.btrfs.subvolume.create(f"/mnt/{subvolume}")
        print(f"Created Subvolume: {subvolume}")

    sh.umount("/mnt")
    
    for subvolume, mount_point in subvolumes.items():
        sh.mkdir("-p", mount_point)
        sh.mount("-o", f"subvol={subvolume}", root_partition, mount_point)
        print(f"Mounted Subvolume: {subvolume} -> {mount_point}")

    sh.mkdir("/mnt/efi")
    sh.mount(efi_partition, "/mnt/efi")

    pacstrap_packages = [
        "base",
        "base-devel",
        "linux",
        "linux-firmware",
        "git",
        "grub",
        "man",
        "sudo",
        "efibootmgr",
    ]
    
    cpu = sh.grep("vendor_id", "/proc/cpuinfo")

    if "AutheticAMD" in cpu:
        pacstrap_packages.append("amd-ucode")
    else:
        pacstrap_packages.append("intel-ucode")

    header("Bootstrapping System")

    sh.pacstrap("-K", "/mnt", *pacstrap_packages, _out=stdout)

    header("Creating Fstab")

    sh.genfstab("-U", "/mnt", _out="/mnt/etc/fstab")
    sh.cat("/mnt/etc/fstab", _out=stdout)

    chroot = sh.Command("arch-chroot").bake("/mnt")

    timezone = sh.curl("-s", "http://ip-api.com/line?fields=timezone").strip()
    print(f"Setting Timezone ({timezone})")
    chroot.ln("-sf", f"/usr/share/zoneinfo/{timezone}", "/etc/localtime")
    chroot.hwclock("--systohc")

    print("Generating Locale")
    chroot.sed("-i", "/en_US.UTF-8/s/^#//g", "/etc/locale.gen")
    chroot("locale-gen")

    Path("/mnt/etc/locale.conf").write_text("LANG=en_US.UTF-8")
    Path("/mnt/etc/vconsole.conf").write_text("KEYMAP=us")

    print("Configuring Hosts")
    Path("/mnt/etc/hostname").write_text(hostname)

    with Path("/mnt/etc/hosts").open("w") as hosts:
        hosts.write("127.0.0.1 localhost")
        hosts.write("::1 localhost")
        hosts.write(f"127.0.1.1 {hostname}")

    print("Creating User")
    chroot.useradd("-mG", "wheel", username)
    chroot.passwd(username, "--stdin", _in=sh.echo(password))

    chroot("grub-install", "--target", "x86_64-efi", "--efi-directory", "/efi", "--bootloader-id", "GRUB")
    chroot("grub-mkconfig", "-o", "/boot/grub/grub.cfg")

    chroot.echo("%wheel ALL=(ALL:ALL) ALL", _out=Path("/mnt/etc/sudoers").open("a"))

    print("Installing aura")
    chroot.git.clone("https://aur.archlinux.org/aura.git", f"/home/{username}", _out=stdout)
    chroot.sudo("-u", username, "--", "makepkg", "--dir", f"/home/{username}/aura", "-si", _out=stdout)
    chroot.rm("-rf", f"/home/{username}/aura")

if __name__ == "__main__":
    main()
