Baldur
======

*Managed File Transfer (MFT) Download Client and Library*

Baldur helps you successfully download large files over HTTP. Large files can easily get corrupted when downloaded over the internet, even over high quality connections, but especially over marginal connections.

Other MFT solutions create their own transfer protocol over UDP by using custom server software. That is a good solution for some use cases, but is expensive and doesn't necessarily scale well.

Baldur uses simple HTTP, which allows the use of cheap and readily available HTTP servers, and for full compatibility with content delivery networks (CDN).

###NOTE: The code is in a usable state, but is of alpha quality, expect bugs.

##How it works

Baldur is composed of 2 basic components.

* File analyzer (fractional hasher)
* File downloader

###File Analyzer (frac_hasher.py)
The file analyzer creates a md5 hash for every x number of megabytes of the file you want to be managed. The default is 5MB. These hashes, along with the total number of hashes, and the complete file hash, is stored in a .frac file.

###File Downloader (baldur.py)
The file downloader takes the .frac file and a HTTP link to work. The link can be to any HTTP server that supports the Range header. The file downloader works by downloading every chunk from the .frac file, and checking the md5 hash once it has finished downloading. Because it downloads the file in many chunks it can download multiple chunks and once, possibly greatly decreasing the download time. If any chunks are corrupt they are re-downloaded.

The advantage of this method over traditional downloads is that if any bits are corrupted while downloading only a small portion needs to be re-downloaded. Using a traditional download if even a single bit if corrupted during the download, the entire file must be re-downloaded. Which can take a lot of time for large files. 

##How to use

1. Create a .frac file of the file you want to download.

   You can use the frac_hasher.py Python script, or you can use the javascript version [here](http://bantonj.github.io/Baldur/). The Python script is much faster.

    frac_hasher.py -m somefile.file -f somefile.frac

2. Use the baldur.py Python script to download the file.

    baldur.py -f somefile.frac -l http://example.com/static/somefile.file -d /path/to/directory
