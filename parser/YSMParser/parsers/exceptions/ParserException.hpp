#pragma once
#include <exception>
class ParserUnSupportVersionException : public std::exception {
public:
	ParserUnSupportVersionException() noexcept = default;
	~ParserUnSupportVersionException() noexcept override = default;
	const char* what() const noexcept override
	{
		return "Unsupported file version detected";
	}
};

class ParserInvalidFileFormatException : public std::exception {
public:
	ParserInvalidFileFormatException() noexcept = default;
	~ParserInvalidFileFormatException() noexcept override = default;
	const char* what() const noexcept override
	{
		return "Unsupported file format detected";
	}
};


class ParserCorruptedDataException : public std::exception {
public:
	ParserCorruptedDataException() noexcept = default;
	~ParserCorruptedDataException() noexcept override = default;
	const char* what() const noexcept override
	{
		return "File Corrupted";
	}
};


class ParserIndexOutOfBoundException : public std::exception {
public:
	ParserIndexOutOfBoundException() noexcept = default;
	~ParserIndexOutOfBoundException() noexcept override = default;
	const char* what() const noexcept override
	{
		return "Index Out Of Bound, Maybe Decryption Error";
	}
};

class ParserUnknownField : public std::exception {
public:
	ParserUnknownField() noexcept = default;
	~ParserUnknownField() noexcept override = default;
	const char* what() const noexcept override
	{
		return "Unknown field encountered";
	}
};


class ParserPathNotSupported : public std::exception {
public:
	ParserPathNotSupported() noexcept = default;
	~ParserPathNotSupported() noexcept override = default;
	const char* what() const noexcept override
	{
		return "Path not supported";
	}
};


